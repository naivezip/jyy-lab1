"""Tools are registered here; each module exports TOOLS."""

from __future__ import annotations

from assistant.tools.base import Tool, ToolSpec


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.spec.name: tool for tool in tools}

    @property
    def specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)


def default_registry(cwd: str) -> ToolRegistry:
    from assistant.tools import bash, fd, grep, read, write

    return ToolRegistry([
        read.build(cwd),
        write.build(cwd),
        bash.build(cwd),
        fd.build(cwd),
        grep.build(cwd),
    ])
