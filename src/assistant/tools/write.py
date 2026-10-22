"""write: create or overwrite a file."""

from __future__ import annotations

from assistant.tools.base import Tool, ToolSpec
from assistant.tools.fsutil import resolve


def build(cwd: str) -> Tool:
    def handler(path: str, content: str) -> str:
        target = resolve(cwd, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        target.write_bytes(data)
        return f"Wrote {len(data)} bytes to {path}"

    return Tool(
        spec=ToolSpec(
            name="write",
            description=(
                "Write a file, creating parent directories as needed. "
                "Overwrites the file if it exists."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to cwd or absolute)"},
                    "content": {"type": "string", "description": "Full file content"},
                },
                "required": ["path", "content"],
            },
        ),
        handler=handler,
    )
