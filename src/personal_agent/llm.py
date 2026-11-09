"""DeepSeek chat-completions streaming through the OpenAI SDK."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import openai
from openai import OpenAI

from .config import Config
from .tools.bash import BASH_TOOL_SPEC


class LLMError(Exception):
    """A model request failed with a message suitable for the terminal."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ReasoningDelta:
    text: str


@dataclass(frozen=True)
class Notice:
    text: str


@dataclass(frozen=True)
class StepEnd:
    message: dict[str, Any]
    usage: Usage
    finish_reason: str | None


StreamEvent = TextDelta | ReasoningDelta | Notice | StepEnd


def _reasoning_text(delta: Any) -> str | None:
    text = getattr(delta, "reasoning_content", None)
    if text is None:
        extra = getattr(delta, "model_extra", None) or {}
        text = extra.get("reasoning_content")
    return text or None


def stream_step(config: Config, history: list[dict[str, Any]]) -> Iterator[StreamEvent]:
    """Stream one model step and yield deltas followed by exactly one StepEnd."""
    client = OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        max_retries=0,
    )
    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": history,
        "tools": [BASH_TOOL_SPEC],
        "stream": True,
        "stream_options": {"include_usage": True},
        "reasoning_effort": config.reasoning_effort,
        "extra_body": {"thinking": {"type": "enabled"}},
    }

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    calls: dict[int, dict[str, str]] = {}
    finish_reason: str | None = None
    usage = Usage()

    try:
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            if chunk.usage:
                usage = Usage(
                    input_tokens=chunk.usage.prompt_tokens or 0,
                    output_tokens=chunk.usage.completion_tokens or 0,
                )
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            reasoning = _reasoning_text(delta)
            if reasoning:
                reasoning_parts.append(reasoning)
                yield ReasoningDelta(reasoning)

            if delta.content:
                content_parts.append(delta.content)
                yield TextDelta(delta.content)

            for call_delta in delta.tool_calls or []:
                slot = calls.setdefault(
                    call_delta.index,
                    {"id": "", "name": "", "arguments": ""},
                )
                if call_delta.id:
                    slot["id"] = call_delta.id
                function = call_delta.function
                if function is not None:
                    if function.name:
                        slot["name"] += function.name
                    if function.arguments:
                        slot["arguments"] += function.arguments

            if choice.finish_reason:
                finish_reason = choice.finish_reason
    except openai.APIError as exc:
        raise LLMError(f"DeepSeek request failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - network and protocol failures both surface here
        raise LLMError(f"DeepSeek request failed: {type(exc).__name__}: {exc}") from exc

    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(content_parts) or None,
        "reasoning_content": "".join(reasoning_parts),
    }
    if calls:
        message["tool_calls"] = [
            {
                "id": calls[index]["id"] or f"call_{index}",
                "type": "function",
                "function": {
                    "name": calls[index]["name"],
                    "arguments": calls[index]["arguments"],
                },
            }
            for index in sorted(calls)
        ]

    if finish_reason == "length":
        yield Notice("Response hit max_tokens and was truncated.")

    yield StepEnd(message=message, usage=usage, finish_reason=finish_reason)
