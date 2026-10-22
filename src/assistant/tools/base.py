"""Tool registry primitives shared by the provider adapters and the agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

MAX_TOOL_OUTPUT = 16_000


@dataclass(frozen=True)
class ToolSpec:
    """What the model sees."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    handler: Callable[..., str]

    def run(self, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Execute and return (content, is_error). Never raises."""
        try:
            return str(self.handler(**arguments)), False
        except Exception as exc:  # noqa: BLE001 - report every failure to the model
            return f"{type(exc).__name__}: {exc}", True


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n\n[truncated: {omitted} more characters omitted]"
