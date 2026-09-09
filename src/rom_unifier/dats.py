from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import Settings
from .downloads import fetch, safe_extract
from .registry import Platform


def sync(settings: Settings, names: list[str] | None = None):
    dat_root = settings.paths["dats"]
    sources = settings.data.get("dat_sources", [])
    selected = [item for item in sources if not names or item["name"] in names]
    for item in selected:
        destination = dat_root / item["destination"]
        with tempfile.TemporaryDirectory() as temp_name:
            archive = fetch(item["url"], Path(temp_name) / "download", item.get("sha256", ""))
            kind = item.get("archive", "plain")
            if kind == "plain":
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(archive, destination)
            else:
                safe_extract(archive, destination, kind, item.get("subdirectory", ""))
        print(f"SYNCED: {item['name']}: {destination}")


def filter_clrmamepro(source: Path, target: Path, extension: str) -> int:
    text = source.read_text(encoding="utf-8")
    parts = re.split(r"(?=^game \($)", text, flags=re.MULTILINE)
    matcher = re.compile(rf'rom \( name "[^"]+\.{re.escape(extension)}"', re.IGNORECASE)
    games = [block for block in parts[1:] if matcher.search(block)]
    if not games:
        raise ValueError(f"no .{extension} records found in {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(parts[0] + "".join(games), encoding="utf-8")
    return len(games)


def prepare(settings: Settings, platform: Platform, user_config: Path):
    if not platform.dat:
        raise ValueError(f"{platform.id} requires a {platform.dat_family or 'platform-specific'} DAT")
    raw = settings.paths["dats"] / "raw/no-intro" / platform.dat
    filtered = settings.paths["dats"] / "filtered" / f"{platform.id}-{platform.canonical_extension}.dat"
    count = filter_clrmamepro(raw, filtered, platform.canonical_extension)
    output = settings.paths["dats"] / "1g1r" / platform.id
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    spec = settings.tool("retool")
    command = [spec.get("python", "python3"), spec["path"], str(filtered), "--config", str(user_config), "--output", str(output), "--report", "--listnames"]
    subprocess.run(command, check=True)
    print(f"PREPARED: {platform.id}: {count} canonical records -> {output}")
