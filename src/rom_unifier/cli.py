from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import inventory, simple
from .config import load as load_config
from .detection import detect
from .registry import load as load_registry


ROOT = Path(__file__).resolve().parents[2]


def parser():
    result = argparse.ArgumentParser(prog="rom-unifier", description="Safely unify incoming ROMs in three steps: inventory, plan, run.")
    result.add_argument("--config", default="config.toml")
    result.add_argument("--registry", default=str(ROOT / "platforms.toml"))
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("platforms", help="list supported platforms, media, and safety gates")
    commands.add_parser("rom-types", help="list supported input and canonical ROM types")
    inv = commands.add_parser("inventory", help="save a reusable source inventory with automatic platform detections")
    inv.add_argument("--output", type=Path)
    plan = commands.add_parser("plan", help="save exactly what a future run will unify, back up, or leave blocked")
    plan.add_argument("--output", type=Path, help="also copy the generated plan to this path")
    run = commands.add_parser("run", help="execute a saved plan, or create one automatically when none exists")
    run.add_argument("--plan", type=Path)
    restore = commands.add_parser("restore", help="restore sources and previous destinations from a run backup")
    restore.add_argument("manifest", type=Path)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        settings = load_config(args.config)
        registry = load_registry(args.registry)
        if args.command == "platforms":
            for platform in registry.values():
                print(f"{platform.id}\t{platform.media}\t{platform.output}\t{','.join(platform.requires) or '-'}")
        elif args.command == "rom-types":
            for platform in registry.values():
                print(f"{platform.id}\t{','.join(platform.extensions)}\tcanonical=.{platform.canonical_extension}")
        elif args.command == "inventory":
            runtime = settings.data.get("runtime", {})
            result = inventory.scan(settings.paths["source"], registry, runtime.get("exclude_globs", []))
            result["detections"] = [item.dict() for item in detect(
                settings.paths["source"], registry, settings.paths["dats"],
                runtime.get("detection_sample_files", 5), runtime.get("detection_min_confidence", 0.60)
            )]
            destination = args.output or settings.paths["processing"] / "inventory.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(f"INVENTORY: {destination}")
        elif args.command == "plan":
            target = simple.create_plan(settings, registry)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(target.read_bytes())
                print(f"PLAN_COPY: {args.output}")
        elif args.command == "run":
            plan_file = args.plan or settings.paths["processing"] / "plans/latest.json"
            if not plan_file.exists():
                print("No saved plan found; creating one now.")
                plan_file = simple.create_plan(settings, registry)
            simple.run_plan(settings, registry, plan_file)
        elif args.command == "restore":
            simple.restore(settings, args.manifest)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0
