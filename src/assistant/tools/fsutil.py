"""Filesystem/path helpers shared by the tools."""

from __future__ import annotations

import os
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".uv-cache", ".pytest_cache"}


def resolve(cwd: str, path: str) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path(cwd) / target
    return target


def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\0" in handle.read(1024)
    except OSError:
        return True


def iter_files(root: Path):
    """Yield files under root, skipping noise directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            yield Path(dirpath) / name
