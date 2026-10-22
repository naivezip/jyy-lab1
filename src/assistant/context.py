"""Workspace context: SYSTEM.md plus AGENTS.md files up to the git root."""

from __future__ import annotations

from pathlib import Path

from assistant.prompt import load_system_prompt


def _git_root(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return None


def find_agents_files(cwd: str) -> list[Path]:
    """Collect AGENTS.md from cwd up to the git root, outside-in.

    Outside a git repository only cwd's own AGENTS.md is used, so we never pick
    up unrelated rules from parent directories.
    """
    start = Path(cwd).resolve()
    root = _git_root(start)
    if root is None:
        candidate = start / "AGENTS.md"
        return [candidate] if candidate.is_file() else []

    directories = []
    current = start
    while True:
        directories.append(current)
        if current == root:
            break
        current = current.parent
    files = []
    for directory in reversed(directories):
        candidate = directory / "AGENTS.md"
        if candidate.is_file():
            files.append(candidate)
    return files


def build_system_prompt(cwd: str) -> str:
    parts = [load_system_prompt()]
    for path in find_agents_files(cwd):
        body = path.read_text(encoding="utf-8").strip()
        if body:
            parts.append(f"# Project rules from {path}\n\n{body}")
    return "\n\n".join(parts)
