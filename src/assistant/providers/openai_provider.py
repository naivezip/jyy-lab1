"""OpenAI Chat Completions adapter (also covers DeepSeek/Qwen/vLLM gateways)."""

from __future__ import annotations

import json
from typing import Any, Iterator

import openai
from openai import OpenAI

from assistant.config import Config
from assistant.net import sanitize_proxy_env
from assistant.messages import Message, ThinkingBlock, ToolCall, ToolResult
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


def _convert_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "tool":
            # OpenAI wants one role="tool" message per tool call id.
            for result in msg.tool_results:
                out.append({
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "content": result.content,
                })
            continue

        payload: dict[str, Any] = {"role": msg.role}
        payload["content"] = msg.text or None

        if msg.role == "assistant":
            if msg.thinking:
                # DeepSeek requires reasoning_content echoed on every turn when
                # tools are present; other compatible servers accept or ignore it.
                payload["reasoning_content"] = "".join(b.text for b in msg.thinking)
            if msg.tool_calls:
                payload["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": call.raw_arguments,
                        },
                    }
                    for call in msg.tool_calls
                ]
                if not payload["content"]:
                    payload["content"] = None

        out.append(payload)
    return out


def _convert_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


class OpenAIProvider:
    name = "openai"

    def __init__(self, config: Config) -> None:
        self._config = config
        sanitize_proxy_env()
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            max_retries=0,
        )

    def stream(self, messages: list[Message], tools: list[ToolSpec]) -> Iterator[StreamEvent]:
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": _convert_messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = _convert_tools(tools)

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage = Usage()

        try:
            stream = self._client.chat.completions.create(**kwargs)
            for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = Usage(
                        input_tokens=chunk.usage.prompt_tokens or 0,
                        output_tokens=chunk.usage.completion_tokens or 0,
                    )
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                reasoning = getattr(delta, "reasoning_content", None) or getattr(
                    delta, "reasoning", None
                )
                if reasoning:
                    reasoning_parts.append(reasoning)
                    yield ThinkingDelta(reasoning)

                if delta.content:
                    text_parts.append(delta.content)
                    yield TextDelta(delta.content)

                for call_delta in delta.tool_calls or []:
                    slot = calls.setdefault(
                        call_delta.index,
                        {"id": None, "name": "", "arguments": ""},
                    )
                    if call_delta.id:
                        slot["id"] = call_delta.id
                    if call_delta.function and call_delta.function.name:
                        slot["name"] += call_delta.function.name
                    if call_delta.function and call_delta.function.arguments:
                        slot["arguments"] += call_delta.function.arguments

                if choice.finish_reason:
                    finish_reason = choice.finish_reason
        except openai.APIError as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - connection resets, httpx2 errors
            raise ProviderError(f"OpenAI request failed: {type(exc).__name__}: {exc}") from exc

        tool_calls = []
        for index in sorted(calls):
            slot = calls[index]
            try:
                arguments = json.loads(slot["arguments"]) if slot["arguments"] else {}
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                ToolCall(
                    id=slot["id"] or f"call_{index}",
                    name=slot["name"],
                    arguments=arguments if isinstance(arguments, dict) else {},
                    raw_arguments=slot["arguments"],
                )
            )

        message = Message(
            role="assistant",
            text="".join(text_parts) or None,
            thinking=[ThinkingBlock(text="".join(reasoning_parts))] if reasoning_parts else [],
            tool_calls=tool_calls,
        )
        if finish_reason == "length":
            yield Notice("Response hit max_tokens and was truncated.")
        yield TurnEnd(message=message, usage=usage, stop_reason=finish_reason)


def build(config: Config) -> OpenAIProvider:
    return OpenAIProvider(config)
