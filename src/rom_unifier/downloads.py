from __future__ import annotations

import hashlib
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, destination: Path, expected: str = "") -> Path:
    if not url:
        raise ValueError("download URL is not configured")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    actual = sha256(destination)
    if expected and actual.lower() != expected.lower():
        destination.unlink(missing_ok=True)
        raise ValueError(f"SHA-256 mismatch: expected {expected}, got {actual}")
    if not expected:
        print(f"WARNING: unpinned download; record SHA-256: {actual}")
    return destination


def safe_extract(archive: Path, destination: Path, kind: str, subdirectory: str = ""):
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_name:
        temp = Path(temp_name)
        if kind == "zip":
            with zipfile.ZipFile(archive) as source:
                source.extractall(temp)
        elif kind in {"tar", "tar.gz", "tgz"}:
            with tarfile.open(archive) as source:
                source.extractall(temp, filter="data")
        else:
            raise ValueError(f"unsupported archive type: {kind}")
        root = temp / subdirectory if subdirectory else temp
        if not root.is_dir():
            raise ValueError(f"archive subdirectory not found: {subdirectory}")
        shutil.copytree(root, destination, dirs_exist_ok=True)
