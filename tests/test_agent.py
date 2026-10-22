from __future__ import annotations

import pytest

from assistant.agent import Agent
from assistant.messages import Message, ToolCall
from assistant.providers.base import (
    Notice,
    ProviderError,
    TextDelta,
    ThinkingDelta,
    TurnEnd,
    Usage,
)
from assistant.tools import ToolRegistry
from assistant.tools.base import Tool, ToolSpec


class ScriptedProvider:
    """Returns pre-scripted turns in order."""

    name = "fake"

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def stream(self, messages, tools):
        self.calls.append((len(messages), [t.name for t in tools]))
        if not self.turns:
            raise AssertionError("provider called more times than scripted")
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        if isinstance(turn, str):
            yield TextDelta(turn)
            yield TurnEnd(Message(role="assistant", text=turn), Usage(1, 1), "stop")
            return
        message, usage = turn
        if message.text:
            yield TextDelta(message.text)
        for block in message.thinking:
            if block.visible:
                yield ThinkingDelta(block.text)
        yield TurnEnd(message, usage or Usage(1, 1), "tool_calls" if message.tool_calls else "stop")


def echo_tool():
    return Tool(
        spec=ToolSpec(name="echo", description="Echo", parameters={"type": "object"}),
        handler=lambda text: f"echo:{text}",
    )


def boom_tool():
    def handler(**kwargs):
        raise ValueError("kaboom")

    return Tool(
        spec=ToolSpec(name="boom", description="Boom", parameters={"type": "object"}),
        handler=handler,
    )


def assistant_call(*calls):
    return Message(role="assistant", tool_calls=list(calls))


def test_plain_answer_ends_in_one_turn():
    provider = ScriptedProvider(["hello"])
    agent = Agent(provider, ToolRegistry([]), max_steps=5)
    history = [Message(role="user", text="hi")]

    result = agent.run(history)

    assert result.stopped_reason == "completed"
    assert history[-1].text == "hello"
    assert len(provider.calls) == 1


def test_single_tool_call_feeds_result_back():
    provider = ScriptedProvider([
        (assistant_call(ToolCall(id="c1", name="echo", arguments={"text": "x"})), None),
        "done",
    ])
    registry = ToolRegistry([echo_tool()])
    agent = Agent(provider, registry)
    history = [Message(role="user", text="hi")]

    result = agent.run(history)

    assert result.stopped_reason == "completed"
    tool_msg = history[2]
    assert tool_msg.role == "tool"
    assert tool_msg.tool_results[0].content == "echo:x"
    assert not tool_msg.tool_results[0].is_error
    assert provider.calls[1][0] == 3  # user + assistant + tool result


def test_parallel_tool_calls_are_all_executed():
    provider = ScriptedProvider([
        (assistant_call(
            ToolCall(id="c1", name="echo", arguments={"text": "a"}),
            ToolCall(id="c2", name="echo", arguments={"text": "b"}),
        ), None),
        "done",
    ])
    agent = Agent(provider, ToolRegistry([echo_tool()]))
    history = [Message(role="user", text="hi")]

    agent.run(history)

    results = history[2].tool_results
    assert [r.content for r in results] == ["echo:a", "echo:b"]
    assert [r.tool_call_id for r in results] == ["c1", "c2"]


def test_tool_exception_is_reported_not_raised():
    provider = ScriptedProvider([
        (assistant_call(ToolCall(id="c1", name="boom", arguments={})), None),
        "recovered",
    ])
    agent = Agent(provider, ToolRegistry([boom_tool()]))
    history = [Message(role="user", text="hi")]

    result = agent.run(history)

    assert result.stopped_reason == "completed"
    tool_result = history[2].tool_results[0]
    assert tool_result.is_error
    assert "kaboom" in tool_result.content


def test_unknown_tool_is_reported():
    provider = ScriptedProvider([
        (assistant_call(ToolCall(id="c1", name="nope", arguments={})), None),
        "ok",
    ])
    agent = Agent(provider, ToolRegistry([echo_tool()]))
    history = [Message(role="user", text="hi")]

    agent.run(history)

    assert "Unknown tool" in history[2].tool_results[0].content
    assert history[2].tool_results[0].is_error


def test_malformed_json_arguments_never_reach_handler():
    provider = ScriptedProvider([
        (assistant_call(ToolCall(id="c1", name="echo", arguments={}, raw_arguments='{"text"')), None),
        "ok",
    ])
    agent = Agent(provider, ToolRegistry([echo_tool()]))
    history = [Message(role="user", text="hi")]

    agent.run(history)

    assert "Invalid JSON" in history[2].tool_results[0].content


def test_step_limit_forces_tool_free_final_answer():
    turns = []
    for _ in range(3):
        turns.append((assistant_call(ToolCall(id="c1", name="echo", arguments={"text": "x"})), None))
    turns.append("final")
    provider = ScriptedProvider(turns)
    agent = Agent(provider, ToolRegistry([echo_tool()]), max_steps=3)
    history = [Message(role="user", text="hi")]

    result = agent.run(history)

    assert result.stopped_reason == "step_limit"
    assert history[-1].text == "final"
    assert provider.calls[-1][1] == []  # no tools offered on the last turn


def test_notice_events_are_forwarded():
    seen = []
    agent = Agent(ScriptedProvider(["hi"]), ToolRegistry([]), on_event=seen.append)
    agent.run([Message(role="user", text="q")])
    assert any(isinstance(e, TextDelta) for e in seen)


def test_provider_error_propagates_without_mutating_history():
    provider = ScriptedProvider([ProviderError("auth failed")])
    agent = Agent(provider, ToolRegistry([]))
    history = [Message(role="user", text="hi")]

    with pytest.raises(ProviderError):
        agent.run(history)

    assert len(history) == 1
