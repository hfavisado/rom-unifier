from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import dats as dat_ops
from . import playlists, tooling
from .config import Settings
from .detection import detect
from .registry import Platform


def _fingerprint(folder: Path):
    files = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        stat = path.stat()
        files.append({"path": str(path.relative_to(folder)), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return files


def create_plan(settings: Settings, registry: dict[str, Platform]) -> Path:
    paths = settings.paths
    source = paths["source"]
    if not source.is_dir():
        raise FileNotFoundError(f"configured source does not exist: {source}")
    runtime = settings.data.get("runtime", {})
    found = detect(source, registry, paths["dats"], runtime.get("detection_sample_files", 5), runtime.get("detection_min_confidence", 0.60))
    grouped = defaultdict(list)
    for item in found:
        grouped[registry[item.platform].output].append(item)
    operations = []
    claimed = set()
    for output, items in sorted(grouped.items()):
        folders = []
        for item in sorted(items, key=lambda value: len(Path(value.folder).parts)):
            folder = Path(item.folder)
            if any(parent in folder.parents or parent == folder for parent in claimed):
                continue
            claimed.add(folder)
            folders.append(folder)
        if not folders:
            continue
        platform_ids = sorted({item.platform for item in items})
        platforms = [registry[ident] for ident in platform_ids]
        final = paths["destination"] / output
        destination_snapshot = _fingerprint(final) if final.is_dir() else []
        destination_names = {item["path"].casefold() for item in destination_snapshot}
        destination_basenames = {Path(name).name.casefold() for name in destination_names}
        candidate_actions = []
        for folder in folders:
            for item in _fingerprint(folder):
                candidate_actions.append({
                    "source": str(folder / item["path"]),
                    "action": "candidate-deduplicate" if Path(item["path"]).name.casefold() in destination_basenames else "candidate-add",
                    "reason": "same filename exists in destination; DAT identity decides" if Path(item["path"]).name.casefold() in destination_basenames else "filename not present in destination; DAT validation still required",
                })
        blockers = sorted({reason for platform in platforms for reason in platform.requires})
        if any(platform.normalizer for platform in platforms):
            blockers.append("media-normalizer")
        operations.append({
            "output": output, "platforms": platform_ids, "media": sorted({p.media for p in platforms}),
            "source_folders": [{"path": str(folder), "snapshot": _fingerprint(folder)} for folder in folders],
            "destination": str(final), "existing_destination": destination_snapshot,
            "candidate_actions": candidate_actions,
            "blockers": sorted(set(blockers)),
            "reason": f"merge {len(folders)} detected source folder(s) into canonical {final}",
            "evidence": [item.dict() for item in items],
        })
    payload = {
        "schema": 1, "created": datetime.now(timezone.utc).isoformat(),
        "source": str(source), "destination": str(paths["destination"]), "operations": operations,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["plan_sha256"] = hashlib.sha256(canonical).hexdigest()
    plan_dir = paths["processing"] / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    target = plan_dir / f"plan-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    target.write_text(text, encoding="utf-8")
    (plan_dir / "latest.json").write_text(text, encoding="utf-8")
    print(f"PLAN: {target}")
    print(f"OPERATIONS: {len(operations)}")
    for operation in operations:
        status = "BLOCKED: " + ", ".join(operation["blockers"]) if operation["blockers"] else "READY"
        print(f"{operation['output']}: {status}: {operation['reason']}")
    return target


def _validate_plan(settings: Settings, payload: dict):
    if payload["source"] != str(settings.paths["source"]) or payload["destination"] != str(settings.paths["destination"]):
        raise RuntimeError("saved plan paths do not match current configuration; create a new plan")
    unsigned = {key: value for key, value in payload.items() if key != "plan_sha256"}
    digest = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != payload["plan_sha256"]:
        raise RuntimeError("saved plan was modified; create a new plan")
    for operation in payload["operations"]:
        final = Path(operation["destination"])
        current_destination = _fingerprint(final) if final.is_dir() else []
        if current_destination != operation["existing_destination"]:
            raise RuntimeError(f"destination changed since planning: {final}; create a new plan")
        for source in operation["source_folders"]:
            folder = Path(source["path"])
            if not folder.is_dir() or _fingerprint(folder) != source["snapshot"]:
                raise RuntimeError(f"source changed since planning: {folder}; create a new plan")


def _ensure_tool(settings: Settings, name: str) -> str:
    spec = settings.tool(name)
    path = Path(spec["path"])
    if not path.exists():
        tooling.sync(settings, [name])
    if not path.is_file() or not os.access(path, os.X_OK):
        raise FileNotFoundError(f"configure an executable [tools.{name}].path or download recipe; unavailable: {path}")
    return str(path)


def _dats_for(settings: Settings, platform: Platform) -> list[Path]:
    root = settings.paths["dats"]
    prepared = sorted((root / "1g1r" / platform.id).rglob("*.dat"))
    if prepared:
        return prepared
    if platform.dat_family == "redump":
        result = sorted((root / "raw/redump" / platform.id).rglob("*.dat"))
        if not result:
            raise FileNotFoundError(f"configure and sync a Redump DAT for {platform.id}")
        return result
    raw = root / "raw/no-intro" / str(platform.dat)
    if not raw.exists():
        dat_ops.sync(settings, ["libretro-no-intro"])
    retool_config = settings.data.get("runtime", {}).get("retool_config", "")
    if not retool_config:
        raise ValueError("set [runtime].retool_config to create parent/clone 1G1R DATs")
    retool = settings.tool("retool")
    if not Path(retool["path"]).is_file() or not Path(retool["python"]).is_file():
        tooling.sync(settings, ["retool"])
    dat_ops.prepare(settings, platform, Path(retool_config))
    return sorted((root / "1g1r" / platform.id).rglob("*.dat"))


def _run_logged(command: list[str], log: Path):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(line, end="")
            handle.write(line)
        code = process.wait()
    content = log.read_text(encoding="utf-8", errors="replace")
    if code or "ERROR:" in content or "Emitted 'error' event" in content:
        raise RuntimeError(f"command failed; inspect {log}")


def run_plan(settings: Settings, registry: dict[str, Platform], plan_file: Path):
    payload = json.loads(plan_file.read_text(encoding="utf-8"))
    _validate_plan(settings, payload)
    blocked = [op for op in payload["operations"] if op["blockers"]]
    for operation in blocked:
        print(f"SKIPPED_BLOCKED: {operation['output']}: {', '.join(operation['blockers'])}")
    ready = [op for op in payload["operations"] if not op["blockers"]]
    if not ready:
        raise RuntimeError("plan has no runnable operations; resolve the reported platform requirements")
    igir = _ensure_tool(settings, "igir")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    work = settings.paths["processing"] / "runs" / run_id
    backup = settings.paths["backups"] / run_id
    staged = []
    for operation in ready:
        platforms = [registry[name] for name in operation["platforms"]]
        media = set(operation["media"])
        if len(media) != 1 or next(iter(media)) not in {"cartridge", "disc"}:
            raise RuntimeError(f"unsupported mixed/special media operation: {operation['output']}")
        stage = settings.paths["staging"] / run_id / operation["output"]
        stage.mkdir(parents=True, exist_ok=False)
        dat_files = [dat for platform in platforms for dat in _dats_for(settings, platform)]
        command = [igir, "copy"] + (["zip"] if "cartridge" in media else []) + ["report"]
        for dat in dat_files:
            command += ["--dat", str(dat)]
        for source in operation["source_folders"]:
            command += ["--input", source["path"]]
        final = Path(operation["destination"])
        if final.exists():
            command += ["--input", str(final)]
        command += ["--output", str(stage), "--reader-threads", str(settings.data["runtime"].get("reader_threads", 2)),
                    "--writer-threads", str(settings.data["runtime"].get("writer_threads", 1)),
                    "--report-output", str(work / "reports" / f"{operation['output']}.csv")]
        for platform in platforms:
            for ext in platform.remove_headers:
                command += ["--remove-headers", ext]
        _run_logged(command, work / "logs" / f"{operation['output']}-stage.log")
        verify = [igir, "test", "report"]
        for dat in dat_files:
            verify += ["--dat", str(dat)]
        verify += ["--input", str(stage), "--reader-threads", str(settings.data["runtime"].get("reader_threads", 2)),
                   "--report-output", str(work / "reports" / f"{operation['output']}-verify.csv")]
        _run_logged(verify, work / "logs" / f"{operation['output']}-verify.log")
        if "disc" in media and any(platform.playlist for platform in platforms):
            playlists.build(stage, execute=True)
            playlists.verify(stage)
        staged.append((operation, stage))
    restore = {"run_id": run_id, "operations": []}
    for operation, stage in staged:
        final = Path(operation["destination"])
        record = {"platform": operation["output"], "final": str(final), "sources": []}
        if final.exists():
            previous = backup / operation["output"] / "previous-final"
            previous.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(final), str(previous))
            record["previous_final"] = str(previous)
        for index, source in enumerate(operation["source_folders"], 1):
            original = Path(source["path"])
            saved = backup / operation["output"] / "sources" / f"{index:03d}-{original.name}"
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(original), str(saved))
            record["sources"].append({"original": str(original), "backup": str(saved)})
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stage), str(final))
        record["new_final"] = str(final)
        restore["operations"].append(record)
        print(f"UNIFIED: {operation['output']} -> {final}")
    restore_file = backup / "restore.json"
    restore_file.parent.mkdir(parents=True, exist_ok=True)
    restore_file.write_text(json.dumps(restore, indent=2) + "\n", encoding="utf-8")
    (work / "complete.json").write_text(json.dumps({"plan": str(plan_file), "backup": str(backup)}, indent=2) + "\n")
    print(f"BACKUP: {backup}")
    print(f"RESTORE_MANIFEST: {restore_file}")


def restore(settings: Settings, manifest: Path):
    manifest = manifest.resolve()
    backup_root = settings.paths["backups"].resolve()
    if not manifest.is_relative_to(backup_root):
        raise RuntimeError(f"restore manifest must be beneath configured backups: {backup_root}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    restored = manifest.parent / "restored-new-finals"
    for operation in reversed(data["operations"]):
        final = Path(operation["final"])
        if not final.resolve().is_relative_to(settings.paths["destination"].resolve()):
            raise RuntimeError(f"unsafe restore destination outside configured archive: {final}")
        if final.exists():
            target = restored / operation["platform"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(final), str(target))
        previous = operation.get("previous_final")
        if previous and Path(previous).exists():
            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(previous, final)
        for source in operation["sources"]:
            original, saved = Path(source["original"]), Path(source["backup"])
            if not original.resolve().is_relative_to(settings.paths["source"].resolve()) or not saved.resolve().is_relative_to(manifest.parent.resolve()):
                raise RuntimeError(f"unsafe restore path in manifest: {original} <- {saved}")
            if original.exists():
                raise RuntimeError(f"cannot restore over existing source: {original}")
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(saved), str(original))
        print(f"RESTORED: {operation['platform']}")
