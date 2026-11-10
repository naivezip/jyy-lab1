"""The ReAct loop: stream a step, run tools, feed observations back, repeat."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from .config import Config
from .llm import (
    LLMError,
    Notice,
    ReasoningDelta,
    StepEnd,
    TextDelta,
    stream_step,
)
from .tools import BashTool, EditTool, ReadTool, WriteTool


@dataclass(frozen=True)
class ToolStart:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolEnd:
    call_id: str
    name: str
    content: str
    is_error: bool


AgentEvent = TextDelta | ReasoningDelta | Notice | StepEnd | ToolStart | ToolEnd


class Agent:
    """One conversation. The caller owns the message history."""

    def __init__(self, config: Config, cwd: str) -> None:
        self._config = config
        self._tools = {
            "bash": BashTool(cwd),
            "read": ReadTool(cwd),
            "write": WriteTool(cwd),
            "edit": EditTool(cwd),
        }

    def run(self, history: list[dict[str, Any]]) -> Iterator[AgentEvent]:
        """Run one turn, appending assistant and tool messages to history."""
        for _ in range(self._config.max_steps):
            step_end: StepEnd | None = None
            for event in stream_step(self._config, history):
                if isinstance(event, StepEnd):
                    step_end = event
                else:
                    yield event

            if step_end is None:
                raise LLMError("Model stream ended without a final step")

            history.append(step_end.message)
            yield step_end

            calls = step_end.message.get("tool_calls") or []
            if not calls:
                return

            for call in calls:
                yield from self._run_tool(call, history)

        yield Notice(f"Step limit ({self._config.max_steps}) reached; stopping.")

    def _run_tool(
        self, call: dict[str, Any], history: list[dict[str, Any]]
    ) -> Iterator[ToolStart | ToolEnd]:
        call_id = str(call.get("id") or "call_unknown")
        function = call.get("function") or {}
        name = str(function.get("name") or "")
        raw_arguments = str(function.get("arguments") or "{}")

        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            yield self._rejected(
                call_id,
                name,
                f"Invalid JSON arguments for {name}: {exc}",
                history,
            )
            return
        if not isinstance(arguments, dict):
            yield self._rejected(
                call_id,
                name,
                f"Arguments for {name} must be a JSON object",
                history,
            )
            return
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(self._tools)
            yield self._rejected(
                call_id,
                name,
                f"Unknown tool {name!r}. Available: {available}",
                history,
            )
            return

        yield ToolStart(call_id=call_id, name=name, arguments=arguments)
        content, is_error = tool.run(arguments)
        yield ToolEnd(call_id=call_id, name=name, content=content, is_error=is_error)
        history.append({"role": "tool", "tool_call_id": call_id, "content": content})

    def _rejected(
        self,
        call_id: str,
        name: str,
        content: str,
        history: list[dict[str, Any]],
    ) -> ToolEnd:
        history.append({"role": "tool", "tool_call_id": call_id, "content": content})
        return ToolEnd(call_id=call_id, name=name, content=content, is_error=True)


__all__ = ["Agent", "AgentEvent", "Notice", "ToolEnd", "ToolStart"]
