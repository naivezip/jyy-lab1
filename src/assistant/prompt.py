"""Package metadata helpers."""

from __future__ import annotations

from pathlib import Path


def system_prompt_path() -> Path:
    """SYSTEM.md ships next to the package; also works from a source checkout."""
    packaged = Path(__file__).with_name("SYSTEM.md")
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[2] / "SYSTEM.md"


def load_system_prompt() -> str:
    path = system_prompt_path()
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "You are a helpful local assistant."
