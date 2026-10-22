"""Provider-neutral conversation model.

Everything the agent loop and the session store touch uses these types. Provider
adapters translate to and from SDK-native shapes; nothing else knows about them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ThinkingBlock:
    """One reasoning block, in provider-native form.

    Anthropic requires `thinking` and `redacted_thinking` blocks to be replayed
    verbatim inside a tool-use turn, so we keep text plus signature/data instead
    of flattening to a string.
    """

    type: Literal["thinking", "redacted_thinking"] = "thinking"
    text: str = ""
    signature: str | None = None
    data: str | None = None

    @property
    def visible(self) -> bool:
        return self.type == "thinking" and bool(self.text)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    # Raw JSON as emitted by the model; kept so a malformed payload can be
    # reported back to the model instead of silently becoming `{}`.
    raw_arguments: str = ""

    def __post_init__(self) -> None:
        if not self.raw_arguments:
            self.raw_arguments = json.dumps(self.arguments, ensure_ascii=False)


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    role: Role
    text: str | None = None
    thinking: list[ThinkingBlock] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "text": self.text,
            "thinking": [
                {k: v for k, v in vars(block).items() if v not in (None, "")}
                for block in self.thinking
            ],
            "tool_calls": [
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                    "raw_arguments": call.raw_arguments,
                }
                for call in self.tool_calls
            ],
            "tool_results": [
                {
                    "tool_call_id": result.tool_call_id,
                    "content": result.content,
                    "is_error": result.is_error,
                }
                for result in self.tool_results
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        return cls(
            role=data["role"],
            text=data.get("text"),
            thinking=[ThinkingBlock(**block) for block in data.get("thinking", [])],
            tool_calls=[ToolCall(**call) for call in data.get("tool_calls", [])],
            tool_results=[ToolResult(**result) for result in data.get("tool_results", [])],
        )


def tool_message(results: list[ToolResult]) -> Message:
    """One provider-neutral tool message may carry several parallel results."""
    return Message(role="tool", tool_results=results)

