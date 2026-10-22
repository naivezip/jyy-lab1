"""Anthropic Messages adapter with adaptive thinking and verbatim thinking replay."""

from __future__ import annotations

import json
from typing import Any, Iterator

import anthropic
from anthropic import Anthropic

from assistant.config import Config
from assistant.messages import Message, ThinkingBlock, ToolCall
from assistant.providers.base import (
    Notice,
    ProviderError,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    TurnEnd,
    Usage,
)
from assistant.tools.base import ToolSpec

THINKING = {"type": "adaptive", "display": "summarized"}


def _convert_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }
        for tool in tools
    ]


def _thinking_blocks(message: Message) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in message.thinking:
        if block.type == "redacted_thinking":
            if block.data:
                blocks.append({"type": "redacted_thinking", "data": block.data})
        elif block.text and block.signature:
            # Only replay a block we can replay faithfully; a missing signature
            # would be rejected as invalid.
            blocks.append(
                {"type": "thinking", "thinking": block.text, "signature": block.signature}
            )
    return blocks


def _convert_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "system":
            continue  # sent as the top-level `system` parameter
        if msg.role == "tool":
            out.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": result.tool_call_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                    for result in msg.tool_results
                ],
            })
            continue

        if msg.role == "assistant":
            content: list[dict[str, Any]] = _thinking_blocks(msg)
            if msg.text:
                content.append({"type": "text", "text": msg.text})
            for call in msg.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.name,
                    "input": call.arguments,
                })
            if not content:
                content = [{"type": "text", "text": "(empty)"}]
            out.append({"role": "assistant", "content": content})
            continue

        out.append({"role": "user", "content": msg.text or ""})
    return out


def _system_text(messages: list[Message]) -> str:
    return "\n\n".join(msg.text for msg in messages if msg.role == "system" and msg.text)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client = Anthropic(
            api_key=config.api_key,
            base_url=config.base_url,
            max_retries=0,
        )
        self._thinking: dict[str, Any] = dict(THINKING)

    def stream(self, messages: list[Message], tools: list[ToolSpec]) -> Iterator[StreamEvent]:
        try:
            yield from self._stream_once(messages, tools)
        except _ThinkingRejected:
            # `adaptive` is rejected on 4.5-era models; degrade instead of dying.
            self._thinking = {}
            yield Notice("Thinking is unsupported by this model; continuing without it.")
            yield from self._stream_once(messages, tools)

    def _stream_once(self, messages: list[Message], tools: list[ToolSpec]) -> Iterator[StreamEvent]:
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens,
            "messages": _convert_messages(messages),
        }
        system = _system_text(messages)
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _convert_tools(tools)
        if self._thinking:
            kwargs["thinking"] = self._thinking

        text_parts: list[str] = []
        blocks: dict[int, dict[str, Any]] = {}
        usage = Usage()
        stop_reason: str | None = None

        try:
            with self._client.messages.stream(**kwargs) as stream:
                for event in stream:
                    if event.type == "message_start":
                        usage.input_tokens = event.message.usage.input_tokens
                    elif event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "thinking":
                            blocks[event.index] = {
                                "type": "thinking",
                                "text": getattr(block, "thinking", "") or "",
                                "signature": getattr(block, "signature", "") or None,
                            }
                        elif block.type == "redacted_thinking":
                            blocks[event.index] = {
                                "type": "redacted_thinking",
                                "data": getattr(block, "data", None),
                            }
                        elif block.type == "text":
                            blocks[event.index] = {"type": "text", "text": ""}
                        elif block.type == "tool_use":
                            blocks[event.index] = {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "json": "",
                            }
                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "thinking_delta":
                            blocks[event.index]["text"] += delta.thinking
                            yield ThinkingDelta(delta.thinking)
                        elif delta.type == "signature_delta":
                            blocks[event.index]["signature"] = delta.signature
                        elif delta.type == "text_delta":
                            blocks[event.index]["text"] += delta.text
                            text_parts.append(delta.text)
                            yield TextDelta(delta.text)
                        elif delta.type == "input_json_delta":
                            blocks[event.index]["json"] += delta.partial_json
                    elif event.type == "message_delta":
                        stop_reason = event.delta.stop_reason
                        if getattr(event, "usage", None):
                            usage.output_tokens = event.usage.output_tokens
        except anthropic.APIError as exc:
            if self._thinking and _is_thinking_rejection(exc):
                raise _ThinkingRejected from exc
            raise ProviderError(f"Anthropic request failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - connection resets etc.
            raise ProviderError(
                f"Anthropic request failed: {type(exc).__name__}: {exc}"
            ) from exc

        thinking: list[ThinkingBlock] = []
        tool_calls: list[ToolCall] = []
        for _, block in sorted(blocks.items()):
            if block["type"] == "thinking":
                thinking.append(
                    ThinkingBlock(
                        type="thinking",
                        text=block["text"],
                        signature=block.get("signature"),
                    )
                )
            elif block["type"] == "redacted_thinking":
                thinking.append(ThinkingBlock(type="redacted_thinking", data=block.get("data")))
            elif block["type"] == "tool_use":
                try:
                    arguments = json.loads(block["json"]) if block["json"] else {}
                except json.JSONDecodeError:
                    arguments = {}
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=arguments if isinstance(arguments, dict) else {},
                        raw_arguments=block["json"],
                    )
                )

        if stop_reason == "max_tokens":
            yield Notice("Response hit max_tokens and was truncated.")

        yield TurnEnd(
            message=Message(
                role="assistant",
                text="".join(text_parts) or None,
                thinking=thinking,
                tool_calls=tool_calls,
            ),
            usage=usage,
            stop_reason=stop_reason,
        )


class _ThinkingRejected(Exception):
    """The model rejected the thinking parameter; retry without it."""


def _is_thinking_rejection(exc: anthropic.APIError) -> bool:
    text = str(exc).lower()
    if "thinking" in text and ("400" in text or "invalid" in text):
        return True
    return isinstance(exc, anthropic.BadRequestError) and "thinking" in text


def build(config: Config) -> AnthropicProvider:
    return AnthropicProvider(config)
