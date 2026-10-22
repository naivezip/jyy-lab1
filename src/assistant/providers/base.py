"""Provider protocol: one streaming call per turn, provider-neutral events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Protocol

from assistant.messages import Message, ToolCall, ToolResult
from assistant.tools.base import ToolSpec


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)


@dataclass
class TextDelta:
    text: str


@dataclass
class ThinkingDelta:
    text: str


@dataclass
class Notice:
    """Non-fatal message for the user (degrade, truncation, ...)."""

    text: str


@dataclass
class ToolStart:
    call: "ToolCall"


@dataclass
class ToolEnd:
    call: "ToolCall"
    result: "ToolResult"


@dataclass
class TurnEnd:
    message: Message
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None


StreamEvent = TextDelta | ThinkingDelta | Notice | ToolStart | ToolEnd | TurnEnd


class ProviderError(Exception):
    """A provider failure with a message suitable for the terminal."""


class Provider(Protocol):
    name: str

    def stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> Iterator[StreamEvent]:
        """Stream one assistant turn. Must end with exactly one TurnEnd."""
        ...
