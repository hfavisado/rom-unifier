from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path

from .registry import Platform


ARCHIVE_EXTENSIONS = {"zip", "7z", "rar", "gz", "xz"}
DISC_TAG = re.compile(r"\s*[\[(](?:disc|disk|cd)\s*\d+[^\])]*[\])]", re.IGNORECASE)
TRAILING_TAGS = re.compile(r"(?:\s*[\[(][^\])]+[\])])+$")
NON_WORD = re.compile(r"[^a-z0-9]+")


def normalized(value: str) -> str:
    return NON_WORD.sub("", value.casefold())


def title_key(filename: str) -> str:
    value = Path(filename).stem
    value = DISC_TAG.sub("", value)
    value = TRAILING_TAGS.sub("", value)
    return normalized(value)


@dataclass
class Detection:
    folder: str
    platform: str
    confidence: float
    files: int
    evidence: list[str]

    def dict(self):
        return asdict(self)


class DatEvidence:
    def __init__(self, dat_root: Path, platforms: dict[str, Platform]):
        self.dat_root = dat_root
        self.platforms = platforms
        self._cache = {}

    def _paths(self, platform: Platform):
        paths = list((self.dat_root / "1g1r" / platform.id).rglob("*.dat"))
        if platform.dat:
            paths += list((self.dat_root / "raw").rglob(platform.dat))
        return list(dict.fromkeys(paths))

    def index(self, platform: Platform):
        if platform.id in self._cache:
            return self._cache[platform.id]
        sha1s, titles = set(), set()
        for path in self._paths(platform):
            text = path.read_text(encoding="utf-8", errors="replace")
            sha1s.update(value.lower() for value in re.findall(r'\bsha1(?:=|\s+)[" ]?([0-9a-fA-F]{40})', text))
            for value in re.findall(r'(?:<game name=|^\s*name\s+)[" ]([^"\n]+)', text, re.MULTILINE):
                key = title_key(value)
                if key:
                    titles.add(key)
        self._cache[platform.id] = (sha1s, titles)
        return sha1s, titles


def _member_extensions(path: Path, limit: int = 25):
    ext = path.suffix.lower().lstrip(".")
    if ext != "zip":
        return [ext]
    try:
        with zipfile.ZipFile(path) as archive:
            return [Path(item.filename).suffix.lower().lstrip(".") for item in archive.infolist() if not item.is_dir()][:limit]
    except (OSError, zipfile.BadZipFile):
        return ["zip"]


def _samples(files: list[Path], platform: Platform, limit: int):
    result = []
    supported = set(platform.extensions) - ARCHIVE_EXTENSIONS
    for path in files:
        if len(result) >= limit:
            break
        ext = path.suffix.lower().lstrip(".")
        if ext in supported:
            result.append((path.name, path.read_bytes() if path.stat().st_size <= 64 * 1024 * 1024 else None))
        elif ext == "zip":
            try:
                with zipfile.ZipFile(path) as archive:
                    for item in archive.infolist():
                        if Path(item.filename).suffix.lower().lstrip(".") in supported:
                            result.append((item.filename, archive.read(item) if item.file_size <= 64 * 1024 * 1024 else None))
                            break
            except (OSError, zipfile.BadZipFile):
                pass
    return result[:limit]


def detect(source: Path, platforms: dict[str, Platform], dat_root: Path, sample_files: int = 5, minimum: float = 0.60):
    alias_map = {}
    ext_map = {}
    for ident, platform in platforms.items():
        for alias in platform.aliases:
            alias_map.setdefault(normalized(alias), set()).add(ident)
        for ext in set(platform.extensions) - ARCHIVE_EXTENSIONS:
            ext_map.setdefault(ext, set()).add(ident)
    evidence = DatEvidence(dat_root, platforms)
    detections = []
    for folder in [source, *(path for path in source.rglob("*") if path.is_dir())]:
        files = [path for path in folder.iterdir() if path.is_file()]
        if not files:
            continue
        alias_candidates = alias_map.get(normalized(folder.name), set())
        observed = []
        for path in files[:100]:
            observed.extend(_member_extensions(path))
        type_candidates = set().union(*(ext_map.get(ext, set()) for ext in observed)) if observed else set()
        candidates = alias_candidates | type_candidates
        best = None
        for ident in candidates:
            platform = platforms[ident]
            supported = set(platform.extensions) - ARCHIVE_EXTENSIONS
            typed = [ext for ext in observed if ext in supported]
            ratio = len(typed) / len(observed) if observed else 0
            score, reasons = 0.0, []
            if ident in alias_candidates:
                score += 0.50
                reasons.append(f"folder alias '{folder.name}'")
            score += 0.35 * ratio
            if ratio:
                reasons.append(f"{len(typed)}/{len(observed)} sampled member types supported")
            unique = sum(1 for ext in set(typed) if len(ext_map.get(ext, ())) == 1)
            if unique:
                score += 0.15
                reasons.append("platform-unique extension")
            sha1s, titles = evidence.index(platform)
            samples = _samples(files, platform, sample_files)
            known = 0
            for name, data in samples:
                if (data is not None and hashlib.sha1(data).hexdigest() in sha1s) or title_key(name) in titles:
                    known += 1
            if samples and known:
                score += 0.25 * known / len(samples)
                reasons.append(f"{known}/{len(samples)} sampled ROMs found in DAT")
            current = Detection(str(folder), ident, round(min(score, 1.0), 3), len(files), reasons)
            if best is None or current.confidence > best.confidence:
                best = current
        if best and best.confidence >= minimum:
            detections.append(best)
    return sorted(detections, key=lambda item: item.folder)
