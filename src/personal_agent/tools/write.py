"""Write tool: create a new text file in the workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fsutil import WorkspacePathError, resolve_workspace_path

WRITE_TOOL_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "write",
        "description": (
            "Create a new text file in the workspace. This tool never modifies "
            "an existing file; use edit for that."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the workspace or absolute inside it",
                },
                "content": {
                    "type": "string",
                    "description": "Exact UTF-8 content for the new file",
                },
            },
            "required": ["path", "content"],
        },
    },
}


@dataclass(frozen=True)
class WriteTool:
    cwd: str

    def run(self, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Return (observation, is_error). Never raises."""
        raw_path = arguments.get("path")
        content = arguments.get("content")
        if not isinstance(content, str):
            return ("write: 'content' must be a string", True)

        try:
            target = resolve_workspace_path(self.cwd, raw_path)
        except WorkspacePathError as exc:
            return (f"write: {exc}", True)

        if target.exists() or target.is_symlink():
            return (
                f"write: {raw_path} already exists; use edit to modify an existing file",
                True,
            )

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8", newline="") as handle:
                handle.write(content)
        except FileExistsError:
            return (
                f"write: {raw_path} already exists; use edit to modify an existing file",
                True,
            )
        except OSError as exc:
            return (f"write: Could not write {raw_path}: {exc}", True)

        return (f"Wrote {len(content.encode('utf-8'))} bytes to {raw_path}", False)
