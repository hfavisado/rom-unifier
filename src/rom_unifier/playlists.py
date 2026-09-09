from __future__ import annotations

import re
import shutil
from collections import defaultdict
from pathlib import Path


DISC = re.compile(r"^(.*?)\s*(?:[\[(](?:disc|disk|cd)\s*(\d+)(?:\s*of\s*\d+)?[\])]|(?:disc|disk|cd)\s*(\d+))$", re.IGNORECASE)


def groups(root: Path, extension: str = "chd"):
    found = defaultdict(list)
    for path in root.glob(f"*.{extension}"):
        match = DISC.match(path.stem)
        if match:
            found[match.group(1).strip()].append((int(match.group(2) or match.group(3)), path))
    return {title: sorted(discs) for title, discs in found.items() if len(discs) > 1}


def build(root: Path, execute: bool = False):
    plans = groups(root)
    for title, discs in plans.items():
        folder = root / title
        playlist = folder / f"{title}.m3u"
        print(f"{playlist}: " + ", ".join(path.name for _, path in discs))
        if not execute:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        names = []
        for _, source in discs:
            target = folder / source.name
            if target.exists():
                raise FileExistsError(target)
            shutil.move(str(source), str(target))
            names.append(target.name)
        playlist.write_text("\n".join(names) + "\n", encoding="utf-8")
    return len(plans)


def verify(root: Path):
    errors = []
    playlists = list(root.rglob("*.m3u"))
    for playlist in playlists:
        entries = [line.strip() for line in playlist.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        if len(entries) < 2:
            errors.append(f"{playlist}: fewer than two entries")
        for entry in entries:
            target = (playlist.parent / entry).resolve()
            if playlist.parent.resolve() not in target.parents or not target.is_file():
                errors.append(f"{playlist}: missing or unsafe reference: {entry}")
    if errors:
        raise RuntimeError("\n".join(errors))
    print(f"VERIFIED_PLAYLISTS: {len(playlists)}")
    return len(playlists)
