"""Edit tool: replace a 1-based inclusive line range in an existing text file."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fsutil import WorkspacePathError, resolve_workspace_path

EDIT_TOOL_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "edit",
        "description": (
            "Replace a 1-based inclusive line range in an existing text file in "
            "the workspace. Read the file first; use write to create a new file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the workspace or absolute inside it",
                },
                "start": {
                    "type": "integer",
                    "description": "1-based first line to replace",
                },
                "end": {
                    "type": "integer",
                    "description": "1-based last line to replace, inclusive",
                },
                "content": {
                    "type": "string",
                    "description": "Replacement text for the selected lines",
                },
            },
            "required": ["path", "start", "end", "content"],
        },
    },
}


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"'{name}' must be a positive integer")
    return value


def _line_ending(lines: list[str]) -> str:
    for line in lines:
        if line.endswith("\r\n"):
            return "\r\n"
        if line.endswith("\n"):
            return "\n"
        if line.endswith("\r"):
            return "\r"
    return "\n"


def _replacement_lines(content: str, newline: str, *, final_ending: bool) -> list[str]:
    if content == "":
        return []
    lines = [line + newline for line in content.splitlines()]
    if not final_ending and lines:
        lines[-1] = lines[-1].removesuffix(newline)
    return lines


@dataclass(frozen=True)
class EditTool:
    cwd: str

    def run(self, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Return (observation, is_error). Never raises."""
        raw_path = arguments.get("path")
        content = arguments.get("content")
        if not isinstance(content, str):
            return ("edit: 'content' must be a string", True)

        try:
            raw_start = arguments.get("start")
            if raw_start is None:
                raw_start = arguments.get("start_line")
            raw_end = arguments.get("end")
            if raw_end is None:
                raw_end = arguments.get("end_line")
            start = _positive_int(raw_start, "start")
            end = _positive_int(raw_end, "end")
            if end < start:
                return (f"edit: end line {end} is before start line {start}", True)

            target = resolve_workspace_path(self.cwd, raw_path)
            if not target.exists():
                return (
                    f"edit: {raw_path} does not exist; use write to create a new file",
                    True,
                )
            if not target.is_file():
                return (f"edit: Not a file: {raw_path}", True)

            data = target.read_bytes()
            if b"\x00" in data[:1024]:
                return (f"edit: Not a UTF-8 text file: {raw_path}", True)
            text = data.decode("utf-8")
        except WorkspacePathError as exc:
            return (f"edit: {exc}", True)
        except ValueError as exc:
            return (f"edit: {exc}", True)
        except UnicodeDecodeError:
            return (f"edit: Not a UTF-8 text file: {raw_path}", True)
        except OSError as exc:
            return (f"edit: Could not edit {raw_path}: {exc}", True)

        lines = text.splitlines(keepends=True)
        total = len(lines)
        if total == 0:
            return (f"edit: {raw_path} is empty; use write to create content", True)
        if end > total:
            return (f"edit: line range {start}-{end} is past the end ({total} lines)", True)

        replacement = _replacement_lines(
            content,
            _line_ending(lines),
            final_ending=end < total or lines[-1].endswith(("\n", "\r")),
        )
        updated = lines[: start - 1] + replacement + lines[end:]

        try:
            with target.open("w", encoding="utf-8", newline="") as handle:
                handle.write("".join(updated))
        except OSError as exc:
            return (f"edit: Could not edit {raw_path}: {exc}", True)

        return (f"Edited {raw_path}: replaced lines {start}-{end} of {total}", False)
