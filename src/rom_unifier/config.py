from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    file: Path
    data: dict

    @property
    def paths(self) -> dict[str, Path]:
        raw = self.data["paths"]
        source = Path(raw["source"]).expanduser()
        destination = Path(raw["destination"]).expanduser()
        base = destination.parent
        processing = Path(raw.get("processing") or base / "processing/rom-unifier").expanduser()
        backups = Path(raw.get("backups") or base / "backups/rom-unifier").expanduser()
        return {
            "source": source, "destination": destination, "archive": destination,
            "processing": processing,
            "staging": Path(raw.get("staging") or processing / "staging").expanduser(),
            "quarantine": backups, "backups": backups,
            "tools": Path(raw.get("tools") or base / "tools").expanduser(),
            "dats": Path(raw.get("dats") or processing / "dats").expanduser(),
        }

    def tool(self, name: str) -> dict:
        spec = dict(self.data.get("tools", {}).get(name, {}))
        if not spec:
            return spec
        root = self.paths["tools"]
        if not spec.get("path"):
            spec["path"] = str(root / (f"{name}/{name}.py" if name == "retool" else name))
        if name == "retool" and not spec.get("python"):
            spec["python"] = str(root / "retool/.venv/bin/python")
        return spec


def load(path: str | Path) -> Settings:
    file = Path(path).expanduser().resolve()
    with file.open("rb") as handle:
        data = tomllib.load(handle)
    required = {"source", "destination"}
    missing = required - data.get("paths", {}).keys()
    if missing:
        raise ValueError(f"missing [paths] keys: {', '.join(sorted(missing))}")
    empty = [key for key in required if not str(data["paths"].get(key, "")).strip()]
    if empty:
        raise ValueError(
            "configuration required: set absolute [paths] " + ", ".join(sorted(empty)) +
            f" in {file}; no filesystem operation was attempted"
        )
    for key in required:
        candidate = Path(data["paths"][key]).expanduser()
        if not candidate.is_absolute() or candidate == Path(candidate.anchor):
            raise ValueError(f"unsafe [paths].{key}: use a specific absolute directory, not {candidate}")
    if Path(data["paths"]["source"]).expanduser() == Path(data["paths"]["destination"]).expanduser():
        raise ValueError("unsafe configuration: source and destination must be different directories")
    return Settings(file, data)
