from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import Settings
from .downloads import fetch, safe_extract


def status(settings: Settings) -> list[dict]:
    rows = []
    for name, spec in settings.data.get("tools", {}).items():
        path = Path(spec.get("path", "")).expanduser()
        rows.append({"name": name, "path": str(path), "exists": path.exists(), "executable": os.access(path, os.X_OK)})
    return rows


def sync(settings: Settings, names: list[str] | None = None):
    selected = names or list(settings.data.get("tools", {}))
    for name in selected:
        spec = settings.tool(name)
        if not spec:
            raise ValueError(f"unknown tool: {name}")
        target = Path(spec["path"]).expanduser()
        python_target = Path(spec["python"]).expanduser() if spec.get("python") else None
        if target.exists() and (python_target is None or python_target.exists()):
            print(f"OK: {name}: {target}")
            continue
        url, expected, kind = spec.get("url", ""), spec.get("sha256", ""), spec.get("archive", "plain")
        if not url:
            raise FileNotFoundError(f"{name} missing at {target}; configure tools.{name}.url and sha256")
        if not expected:
            raise ValueError(f"refusing unpinned executable download for {name}; configure tools.{name}.sha256")
        with tempfile.TemporaryDirectory() as temp_name:
            downloaded = fetch(url, Path(temp_name) / "download", expected)
            if kind == "plain":
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(downloaded, target)
                target.chmod(0o755)
            else:
                safe_extract(downloaded, target.parent, kind, spec.get("subdirectory", ""))
        if python_target is not None and not python_target.exists():
            environment = python_target.parent.parent
            subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
            subprocess.run([str(environment / "bin/pip"), "install", str(target.parent)], check=True)
        print(f"INSTALLED: {name}: {target}")
