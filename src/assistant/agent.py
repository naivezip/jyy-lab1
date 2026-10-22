"""The ReAct loop: stream a turn, run tools, feed observations back, repeat."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from assistant.messages import Message, ToolResult, tool_message
from assistant.providers.base import (
    Notice,
    Provider,
    ProviderError,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolEnd,
    ToolStart,
    TurnEnd,
    Usage,
)
from assistant.tools import ToolRegistry
from assistant.tools.base import truncate


@dataclass
class LoopResult:
    messages: list[Message]
    usage: Usage
    stopped_reason: str
    context_tokens: int = 0


class Agent:
    """One conversation. History is the caller's; the agent appends to it."""

    def __init__(
        self,
        provider: Provider,
        registry: ToolRegistry,
        max_steps: int = 20,
        on_event: Callable[[StreamEvent], None] | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._max_steps = max_steps
        self._on_event = on_event or (lambda event: None)

    def run(self, history: list[Message]) -> LoopResult:
        """Run until the model produces a final answer, appending to history."""
        total = Usage()
        context_tokens = 0

        for step in range(1, self._max_steps + 1):
            end = self._stream_turn(history, allow_tools=True)
            total = total + end.usage
            context_tokens = end.usage.input_tokens or context_tokens
            history.append(end.message)

            if not end.message.tool_calls:
                return LoopResult(history, total, "completed", context_tokens)

            results = self._execute(end.message.tool_calls)
            history.append(tool_message(results))

        # Step budget exhausted: one last call without tools to force an answer.
        self._on_event(Notice(f"Step limit ({self._max_steps}) reached; asking for a final answer."))
        end = self._stream_turn(history, allow_tools=False)
        total = total + end.usage
        history.append(end.message)
        return LoopResult(history, total, "step_limit", context_tokens)

    def _stream_turn(self, history: list[Message], allow_tools: bool) -> TurnEnd:
        specs = self._registry.specs if allow_tools else []
        for event in self._provider.stream(history, specs):
            self._on_event(event)
            if isinstance(event, TurnEnd):
                return event
        raise ProviderError("Provider stream ended without a final message")

    def _execute(self, calls) -> list[ToolResult]:
        results = []
        for call in calls:
            tool = self._registry.get(call.name)
            if tool is None:
                results.append(
                    ToolResult(
                        tool_call_id=call.id,
                        content=f"Unknown tool {call.name!r}. Available: "
                        + ", ".join(s.name for s in self._registry.specs),
                        is_error=True,
                    )
                )
                continue
            if call.raw_arguments and not call.arguments:
                try:
                    json.loads(call.raw_arguments)
                except json.JSONDecodeError as exc:
                    results.append(
                        ToolResult(
                            tool_call_id=call.id,
                            content=f"Invalid JSON arguments for {call.name}: {exc}",
                            is_error=True,
                        )
                    )
                    continue
            self._on_event(ToolStart(call))
            content, is_error = tool.run(call.arguments)
            self._on_event(ToolEnd(call, ToolResult(tool_call_id=call.id, content=content, is_error=is_error)))
            results.append(
                ToolResult(
                    tool_call_id=call.id,
                    content=truncate(content),
                    is_error=is_error,
                )
            )
        return results


__all__ = ["Agent", "LoopResult", "StreamEvent", "TextDelta", "ThinkingDelta", "TurnEnd"]
