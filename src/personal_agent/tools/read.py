"""Read tool: return numbered lines from a text file in the workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fsutil import WorkspacePathError, resolve_workspace_path

DEFAULT_LINE_LIMIT = 2000

READ_TOOL_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read",
        "description": (
            "Read numbered lines from a text file in the workspace. "
            "Optionally page with a 1-based inclusive start/end line range."
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
                    "description": "1-based first line to return (default 1)",
                },
                "end": {
                    "type": "integer",
                    "description": (
                        "1-based last line to return (default: up to "
                        f"{DEFAULT_LINE_LIMIT} lines from start)"
                    ),
                },
            },
            "required": ["path"],
        },
    },
}


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"'{name}' must be a positive integer")
    return value


def _render(lines: list[str], start: int, end: int, total: int) -> str:
    header = f"lines {start}-{end} of {total}"
    body = "".join(f"{number:>6}\t{line}" for number, line in enumerate(lines, start=start))
    return f"{header}\n{body}"


@dataclass(frozen=True)
class ReadTool:
    cwd: str

    def run(self, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Return (observation, is_error). Never raises."""
        raw_path = arguments.get("path")
        try:
            target = resolve_workspace_path(self.cwd, raw_path)
            if not target.exists():
                return (f"read: No such file: {raw_path}", True)
            if not target.is_file():
                return (f"read: Not a file: {raw_path}", True)

            data = target.read_bytes()
            if b"\x00" in data[:1024]:
                return (f"read: Not a UTF-8 text file: {raw_path}", True)
            text = data.decode("utf-8")
        except WorkspacePathError as exc:
            return (f"read: {exc}", True)
        except UnicodeDecodeError:
            return (f"read: Not a UTF-8 text file: {raw_path}", True)
        except OSError as exc:
            return (f"read: Could not read {raw_path}: {exc}", True)

        lines = text.splitlines(keepends=True)
        total = len(lines)
        if total == 0:
            return (_render([], 0, 0, 0), False)

        try:
            raw_start = arguments.get("start")
            if raw_start is None:
                raw_start = arguments.get("start_line")
            if raw_start is None:
                raw_start = arguments.get("offset", 1)
            start = _positive_int(raw_start, "start")

            raw_end = arguments.get("end")
            if raw_end is None:
                raw_end = arguments.get("end_line")
            if raw_end is None and arguments.get("limit") is not None:
                raw_end = start + _positive_int(arguments.get("limit"), "limit") - 1
            if raw_end is None:
                end = min(start + DEFAULT_LINE_LIMIT - 1, total)
            else:
                end = _positive_int(raw_end, "end")
        except ValueError as exc:
            return (f"read: {exc}", True)

        if start > total:
            return (f"read: start line {start} is past the end ({total} lines)", True)
        if end < start:
            return (f"read: end line {end} is before start line {start}", True)
        end = min(end, total)

        return (_render(lines[start - 1 : end], start, end, total), False)
