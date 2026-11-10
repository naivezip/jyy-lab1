"""Workspace path resolution shared by every file tool."""

from __future__ import annotations

from pathlib import Path


class WorkspacePathError(ValueError):
    """A tool path is invalid or escapes the workspace."""


def resolve_workspace_path(workspace: str | Path, raw_path: object) -> Path:
    """Resolve *raw_path* to a real path that stays inside *workspace*.

    Relative paths resolve from the workspace root. Absolute paths are allowed
    only when their real target is the workspace or a descendant. Symlinks are
    judged by their real target, so a link inside the workspace that points
    outside is rejected.
    """
    root = Path(workspace).resolve()
    if not isinstance(raw_path, str) or not raw_path:
        raise WorkspacePathError("'path' must be a non-empty string")

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        target = candidate.resolve()
    except (OSError, RuntimeError) as exc:
        raise WorkspacePathError(f"cannot resolve {raw_path!r}: {exc}") from exc

    if target != root and root not in target.parents:
        raise WorkspacePathError(f"{raw_path!r} resolves outside the workspace")
    return target
