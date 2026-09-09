from __future__ import annotations

import csv
import fnmatch
import json
from collections import Counter, defaultdict
from pathlib import Path

from .registry import Platform


ARCHIVES = {"zip", "7z", "rar", "gz", "xz"}


def _excluded(path: Path, root: Path, patterns: list[str]) -> bool:
    relative = str(path.relative_to(root))
    return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def scan(root: Path, platforms: dict[str, Platform], exclude_globs: list[str] | None = None) -> dict:
    exclude_globs = exclude_globs or []
    aliases = defaultdict(set)
    extensions = defaultdict(set)
    for ident, platform in platforms.items():
        for alias in platform.aliases:
            aliases[alias.casefold()].add(ident)
        for ext in platform.extensions:
            if ext not in ARCHIVES:
                extensions[ext].add(ident)
    found = defaultdict(lambda: {"files": 0, "bytes": 0, "paths": set(), "extensions": Counter()})
    unknown = Counter()
    total = 0
    for path in root.rglob("*"):
        if not path.is_file() or _excluded(path, root, exclude_globs):
            continue
        total += 1
        ext = path.suffix.lower().lstrip(".")
        candidates = set(extensions.get(ext, ()))
        for part in path.relative_to(root).parts[:-1]:
            candidates.update(aliases.get(part.casefold(), ()))
        if len(candidates) == 1:
            ident = next(iter(candidates))
            item = found[ident]
            item["files"] += 1
            item["bytes"] += path.stat().st_size
            item["paths"].add(str(path.parent))
            item["extensions"][ext or "(none)"] += 1
        else:
            unknown[ext or "(none)"] += 1
    return {
        "root": str(root), "total_files": total,
        "platforms": {key: {**value, "paths": sorted(value["paths"]), "extensions": dict(value["extensions"])} for key, value in sorted(found.items())},
        "unknown_extensions": dict(unknown.most_common()),
    }


def write(result: dict, destination: Path, fmt: str):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return
    with destination.open("w", newline="", encoding="utf-8") as handle:
        out = csv.writer(handle, delimiter="\t")
        out.writerow(["platform", "files", "bytes", "extensions", "paths"])
        for ident, item in result["platforms"].items():
            out.writerow([ident, item["files"], item["bytes"], json.dumps(item["extensions"]), ";".join(item["paths"])])
