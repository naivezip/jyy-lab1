"""grep: search file contents by regular expression."""

from __future__ import annotations

import re

from assistant.tools.base import Tool, ToolSpec, truncate
from assistant.tools.fsutil import is_binary, iter_files, resolve


def build(cwd: str) -> Tool:
    def handler(pattern: str, path: str = ".", include: str | None = None, limit: int = 200) -> str:
        root = resolve(cwd, path)
        if not root.exists():
            raise FileNotFoundError(f"No such path: {path}")

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc

        files = [root] if root.is_file() else list(iter_files(root))
        limit = max(1, int(limit))
        hits: list[str] = []

        for file in files:
            if include and not file.match(include):
                continue
            if file.is_dir() or is_binary(file):
                continue
            try:
                lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, start=1):
                if regex.search(line):
                    display = file if root.is_file() else file.relative_to(root)
                    hits.append(f"{display}:{number}: {line.strip()}")
                    if len(hits) >= limit:
                        break
            if len(hits) >= limit:
                break

        if not hits:
            return f"No matches for {pattern!r} in {path}"
        body = "\n".join(hits)
        if len(hits) >= limit:
            body += f"\n\n[stopped at limit={limit}]"
        return truncate(body)

    return Tool(
        spec=ToolSpec(
            name="grep",
            description="Search file contents with a regular expression. Prints path:line: text.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regular expression"},
                    "path": {"type": "string", "description": "File or directory to search", "default": "."},
                    "include": {"type": "string", "description": "Glob filter for file paths, e.g. '*.py'"},
                    "limit": {"type": "integer", "description": "Maximum matching lines", "default": 200},
                },
                "required": ["pattern"],
            },
        ),
        handler=handler,
    )
