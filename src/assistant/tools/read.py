"""read: view a text file with line numbers."""

from __future__ import annotations

from assistant.tools.base import Tool, ToolSpec, truncate
from assistant.tools.fsutil import is_binary, resolve


def build(cwd: str) -> Tool:
    def handler(path: str, offset: int = 1, limit: int = 2000) -> str:
        target = resolve(cwd, path)
        if not target.is_file():
            raise FileNotFoundError(f"No such file: {path}")
        if is_binary(target):
            raise ValueError(f"Refusing to read binary file: {path}")

        offset = max(1, int(offset))
        limit = max(1, int(limit))
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()

        if offset > len(lines):
            return f"[{path} has {len(lines)} lines; offset {offset} is past the end]"

        window = lines[offset - 1 : offset - 1 + limit]
        numbered = [
            f"{number:>6}\t{line}" for number, line in enumerate(window, start=offset)
        ]
        body = "\n".join(numbered)
        remaining = len(lines) - (offset - 1 + len(window))
        if remaining > 0:
            body += f"\n\n[{remaining} more lines; continue with offset={offset + len(window)}]"
        return truncate(body)

    return Tool(
        spec=ToolSpec(
            name="read",
            description="Read a text file. Returns numbered lines.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to cwd or absolute)"},
                    "offset": {"type": "integer", "description": "1-based first line to read", "default": 1},
                    "limit": {"type": "integer", "description": "Maximum lines to read", "default": 2000},
                },
                "required": ["path"],
            },
        ),
        handler=handler,
    )
