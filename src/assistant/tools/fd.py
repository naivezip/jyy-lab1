"""fd: find files by name pattern (pure Python, no external binary)."""

from __future__ import annotations

import fnmatch
import re

from assistant.tools.base import Tool, ToolSpec, truncate
from assistant.tools.fsutil import iter_files, resolve


def build(cwd: str) -> Tool:
    def handler(pattern: str, path: str = ".", glob: bool = False, limit: int = 200) -> str:
        root = resolve(cwd, path)
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        matcher = (
            (lambda name: fnmatch.fnmatch(name, pattern))
            if glob
            else (lambda name: re.search(pattern, name) is not None)
        )

        limit = max(1, int(limit))
        hits: list[str] = []
        for file in iter_files(root):
            if matcher(file.name):
                hits.append(str(file.relative_to(root)))
                if len(hits) >= limit:
                    break

        if not hits:
            return f"No files matching {pattern!r} under {path}"
        body = "\n".join(hits)
        if len(hits) >= limit:
            body += f"\n\n[stopped at limit={limit}]"
        return truncate(body)

    return Tool(
        spec=ToolSpec(
            name="fd",
            description="Find files by name. Uses a regular expression by default, or a glob.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex (or glob when glob=true) matched against file names"},
                    "path": {"type": "string", "description": "Directory to search", "default": "."},
                    "glob": {"type": "boolean", "description": "Use glob matching instead of regex", "default": False},
                    "limit": {"type": "integer", "description": "Maximum results", "default": 200},
                },
                "required": ["pattern"],
            },
        ),
        handler=handler,
    )
