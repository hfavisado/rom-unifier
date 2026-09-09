#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
"$PYTHON_BIN" -m venv "$repo/.venv"
"$repo/.venv/bin/python" -m pip install --upgrade pip
"$repo/.venv/bin/python" -m pip install -e "$repo"
[[ -e "$repo/config.toml" ]] || cp "$repo/config.example.toml" "$repo/config.toml"
echo "READY: $repo/.venv/bin/rom-unifier"
