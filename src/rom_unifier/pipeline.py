from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .registry import Platform


@dataclass
class Plan:
    platform: str
    inputs: list[Path]
    dats: list[Path]
    staging: Path
    final: Path


def discover_inputs(source: Path, archive: Path, platform: Platform) -> list[Path]:
    aliases = {value.casefold() for value in platform.aliases}
    found = []
    for base in (source, archive):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_dir() and path.name.casefold() in aliases:
                if not any(path == old or old in path.parents for old in found):
                    found.append(path)
    return sorted(found)


def plan(settings: Settings, platform: Platform) -> Plan:
    paths = settings.paths
    dats = sorted((paths["dats"] / "1g1r" / platform.id).rglob("*.dat"))
    return Plan(platform.id, discover_inputs(paths["source"], paths["archive"], platform), dats,
                paths["staging"] / platform.output, paths["archive"] / platform.output)


def _igir(settings: Settings) -> str:
    path = Path(settings.tool("igir").get("path", ""))
    if not path.is_file() or not os.access(path, os.X_OK):
        raise FileNotFoundError(f"IGIR executable unavailable: {path}")
    return str(path)


def stage(settings: Settings, platform: Platform, execute: bool = False):
    item = plan(settings, platform)
    if platform.media != "cartridge":
        raise RuntimeError(f"{platform.id}: use a {platform.media}-specific processor; generic ZIP staging is cartridge-only")
    if platform.requires:
        raise RuntimeError(f"{platform.id} is gated by: {', '.join(platform.requires)}")
    if not item.inputs or not item.dats:
        raise RuntimeError(f"{platform.id}: missing inputs or prepared DAT")
    command = [_igir(settings), "copy", "zip", "report"]
    for dat in item.dats:
        command += ["--dat", str(dat)]
    for source in item.inputs:
        command += ["--input", str(source)]
    command += ["--output", str(item.staging), "--reader-threads", str(settings.data["runtime"].get("reader_threads", 2)),
                "--writer-threads", str(settings.data["runtime"].get("writer_threads", 1)), "--overwrite-invalid",
                "--report-output", str(settings.paths["processing"] / "reports" / f"{platform.id}.csv")]
    for ext in platform.remove_headers:
        command += ["--remove-headers", ext]
    print(" ".join(command))
    if execute:
        item.staging.mkdir(parents=True, exist_ok=True)
        subprocess.run(command, check=True)


def verify(settings: Settings, platform: Platform):
    item = plan(settings, platform)
    report = settings.paths["processing"] / "reports" / f"{platform.id}-verify.csv"
    command = [_igir(settings), "test", "report"]
    for dat in item.dats:
        command += ["--dat", str(dat)]
    command += ["--input", str(item.staging), "--reader-threads", str(settings.data["runtime"].get("reader_threads", 2)), "--report-output", str(report)]
    subprocess.run(command, check=True)
    with report.open(newline="", encoding="utf-8-sig") as handle:
        statuses = {}
        for row in csv.DictReader(handle):
            statuses[row["Status"]] = statuses.get(row["Status"], 0) + 1
    print(json.dumps(statuses, sort_keys=True))


def promotion_manifest(settings: Settings, platforms: list[Platform]) -> tuple[Path, str]:
    payload = {"created": datetime.now(timezone.utc).isoformat(), "operations": []}
    for platform in platforms:
        item = plan(settings, platform)
        if not item.staging.exists():
            continue
        payload["operations"].append({"platform": platform.id, "staging": str(item.staging), "final": str(item.final),
                                      "existing_final_files": sum(1 for p in item.final.rglob("*") if p.is_file()) if item.final.exists() else 0,
                                      "staged_files": sum(1 for p in item.staging.rglob("*") if p.is_file()),
                                      "inputs": [str(p) for p in item.inputs]})
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    target = settings.paths["processing"] / "promotion-manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"MANIFEST: {target}\nAPPROVAL_SHA256: {digest}")
    return target, digest


def promote(settings: Settings, manifest: Path, approval_sha256: str):
    raw = manifest.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != approval_sha256:
        raise RuntimeError(f"approval digest mismatch: manifest is {actual}")
    data = json.loads(raw)
    quarantine = settings.paths["quarantine"] / f"rom-unifier-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    for operation in data["operations"]:
        stage_path, final = Path(operation["staging"]), Path(operation["final"])
        if not stage_path.is_dir():
            raise RuntimeError(f"missing staging: {stage_path}")
        actual_files = sum(1 for p in stage_path.rglob("*") if p.is_file())
        if actual_files != operation["staged_files"]:
            raise RuntimeError(f"staging changed for {operation['platform']}: expected {operation['staged_files']}, got {actual_files}")
        if final.exists():
            target = quarantine / operation["platform"] / "previous-final"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(final), str(target))
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stage_path), str(final))
        for path in final.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        print(f"PROMOTED: {operation['platform']} -> {final}")
    print(f"QUARANTINE: {quarantine}")
