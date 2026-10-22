"""Tests for provider adapters using fake SDK objects (no network)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from assistant.config import Config
from assistant.messages import Message, ThinkingBlock, ToolCall, ToolResult, tool_message
from assistant.providers import openai_provider
from assistant.providers.base import Notice, ProviderError, TextDelta, ThinkingDelta, TurnEnd
from assistant.tools.base import ToolSpec

TOOLS = [ToolSpec(name="read", description="Read a file", parameters={"type": "object"})]


def make_config(**kw):
    base = dict(
        provider="openai", api_key="k", base_url=None, model="m",
        max_tokens=100, max_steps=5, context_window=1000, show_usage=True,
    )
    base.update(kw)
    return Config(**base)


# ---------- OpenAI ----------

def chunk(delta=None, finish=None, usage=None, choices=True):
    choice = SimpleNamespace(delta=delta or SimpleNamespace(
        content=None, tool_calls=None, reasoning_content=None), finish_reason=finish)
    return SimpleNamespace(choices=[choice] if choices else [], usage=usage)


def delta(content=None, tool_calls=None, reasoning=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls, reasoning_content=reasoning)


def tool_delta(index, id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index, id=id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __iter__(self):
        return iter(self._chunks)


def test_openai_streams_text_and_finishes(monkeypatch):
    provider = openai_provider.OpenAIProvider(make_config())
    chunks = [
        chunk(delta(content="Hel")),
        chunk(delta(content="lo"), finish="stop"),
        chunk(choices=False, usage=SimpleNamespace(prompt_tokens=11, completion_tokens=2)),
    ]
    monkeypatch.setattr(provider._client.chat.completions, "create", lambda **kw: FakeStream(chunks))

    events = list(provider.stream([Message(role="user", text="hi")], TOOLS))
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    end = events[-1]

    assert text == "Hello"
    assert isinstance(end, TurnEnd)
    assert end.message.text == "Hello"
    assert end.message.tool_calls == []
    assert end.usage.input_tokens == 11
    assert end.usage.output_tokens == 2


def test_openai_accumulates_tool_call_fragments_by_index(monkeypatch):
    provider = openai_provider.OpenAIProvider(make_config())
    chunks = [
        chunk(delta(tool_calls=[tool_delta(0, id="c1", name="read", arguments='{"pa')])),
        chunk(delta(tool_calls=[tool_delta(0, arguments='th": "a.py"}')])),
        chunk(delta(tool_calls=[tool_delta(1, id="c2", name="bash", arguments='{"command": "ls"}')]),
              finish="tool_calls"),
    ]
    monkeypatch.setattr(provider._client.chat.completions, "create", lambda **kw: FakeStream(chunks))

    events = list(provider.stream([Message(role="user", text="hi")], TOOLS))
    calls = events[-1].message.tool_calls

    assert [c.id for c in calls] == ["c1", "c2"]
    assert calls[0].name == "read"
    assert calls[0].arguments == {"path": "a.py"}
    assert calls[0].raw_arguments == '{"path": "a.py"}'


def test_openai_reports_reasoning_content(monkeypatch):
    provider = openai_provider.OpenAIProvider(make_config())
    chunks = [
        chunk(delta(reasoning="thinking...")),
        chunk(delta(content="done"), finish="stop"),
    ]
    monkeypatch.setattr(provider._client.chat.completions, "create", lambda **kw: FakeStream(chunks))

    events = list(provider.stream([Message(role="user", text="hi")], TOOLS))
    assert any(isinstance(e, ThinkingDelta) and e.text == "thinking..." for e in events)
    assert events[-1].message.thinking[0].text == "thinking..."


def test_openai_malformed_tool_arguments_are_preserved_raw(monkeypatch):
    provider = openai_provider.OpenAIProvider(make_config())
    chunks = [chunk(delta(tool_calls=[tool_delta(0, id="c1", name="read", arguments='{"path"')]),
                    finish="tool_calls")]
    monkeypatch.setattr(provider._client.chat.completions, "create", lambda **kw: FakeStream(chunks))

    call = list(provider.stream([Message(role="user", text="hi")], TOOLS))[-1].message.tool_calls[0]
    assert call.arguments == {}
    assert call.raw_arguments == '{"path"'


def test_openai_wraps_errors(monkeypatch):
    provider = openai_provider.OpenAIProvider(make_config())

    def boom(**kw):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(provider._client.chat.completions, "create", boom)
    with pytest.raises(ProviderError, match="connection reset"):
        list(provider.stream([Message(role="user", text="hi")], TOOLS))


def test_openai_message_conversion_echoes_tool_calls_and_reasoning():
    messages = [
        Message(role="system", text="sys"),
        Message(role="user", text="q"),
        Message(role="assistant", text=None,
                thinking=[ThinkingBlock(text="reason")],
                tool_calls=[ToolCall(id="c1", name="read", arguments={"path": "a"})]),
        tool_message([ToolResult(tool_call_id="c1", content="file body", is_error=False)]),
    ]
    converted = openai_provider._convert_messages(messages)

    assert converted[0]["role"] == "system"
    assistant = converted[2]
    assert assistant["reasoning_content"] == "reason"
    assert assistant["tool_calls"][0]["function"]["arguments"] == '{"path": "a"}'
    assert converted[3] == {"role": "tool", "tool_call_id": "c1", "content": "file body"}


# ---------- Anthropic ----------

def test_anthropic_tool_results_are_one_user_message_in_order():
    from assistant.providers import anthropic_provider

    messages = [
        Message(role="system", text="sys"),
        Message(role="assistant",
                thinking=[ThinkingBlock(text="t", signature="sig")],
                tool_calls=[ToolCall(id="c1", name="read", arguments={"path": "a"})]),
        tool_message([
            ToolResult(tool_call_id="c1", content="ok"),
            ToolResult(tool_call_id="c2", content="bad", is_error=True),
        ]),
    ]
    converted = anthropic_provider._convert_messages(messages)
    assert converted[0]["role"] == "assistant"
    assert converted[0]["content"][0] == {"type": "thinking", "thinking": "t", "signature": "sig"}
    assert converted[0]["content"][1]["type"] == "tool_use"
    assert converted[1]["role"] == "user"
    assert [b["type"] for b in converted[1]["content"]] == ["tool_result", "tool_result"]
    assert converted[1]["content"][1]["is_error"] is True


def test_anthropic_drops_thinking_without_signature():
    from assistant.providers import anthropic_provider

    out = anthropic_provider._convert_messages([
        Message(role="assistant", text="hi", thinking=[ThinkingBlock(text="no sig")])
    ])
    assert out[0]["content"] == [{"type": "text", "text": "hi"}]


def test_anthropic_merges_adjacent_same_role_messages():
    from assistant.providers import anthropic_provider

    out = anthropic_provider._convert_messages([
        Message(role="user", text="one"),
        Message(role="user", text="two"),
        Message(role="assistant", text="three"),
    ])
    assert [m["role"] for m in out] == ["user", "assistant"]
    assert out[0]["content"] == [
        {"type": "text", "text": "one"},
        {"type": "text", "text": "two"},
    ]
