"""Tests for the ReAct loop."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import personal_agent.agent as agent_module
from personal_agent.agent import Agent, ToolEnd, ToolStart
from personal_agent.config import Config
from personal_agent.llm import Notice, StepEnd, TextDelta, Usage
from personal_agent.verify.fake_server import DONE, FakeSSEServer, chunk


def assistant_tool_call(
    name: str,
    arguments: dict[str, Any] | str,
    call_id: str = "call_1",
) -> dict[str, Any]:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {
        "role": "assistant",
        "content": None,
        "reasoning_content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": raw},
            }
        ],
    }


def step(message: dict[str, Any], usage: Usage | None = None) -> StepEnd:
    return StepEnd(message=message, usage=usage or Usage(), finish_reason=None)


def test_tool_call_round_trip_through_real_sdk(tmp_path: Path) -> None:
    first = [
        (0.0, chunk(delta={"reasoning_content": "Run echo."})),
        (
            0.0,
            chunk(
                delta={
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps({"command": "echo hello"}),
                            },
                        }
                    ]
                }
            ),
        ),
        (0.0, chunk(delta={}, finish_reason="tool_calls")),
        (0.0, chunk(usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6})),
        (0.0, DONE),
    ]
    second = [
        (0.0, chunk(delta={"content": "Done."})),
        (0.0, chunk(delta={}, finish_reason="stop")),
        (0.0, chunk(usage={"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9})),
        (0.0, DONE),
    ]

    with FakeSSEServer([first, second]) as server:
        config = Config(
            api_key="test-key",
            model="deepseek-flash",
            base_url=server.base_url,
            max_steps=3,
        )
        agent = Agent(config, str(tmp_path))
        history: list[dict[str, Any]] = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "say hello"},
        ]

        events = list(agent.run(history))
        requests = server.requests

    starts = [event for event in events if isinstance(event, ToolStart)]
    ends = [event for event in events if isinstance(event, ToolEnd)]
    assert len(starts) == 1
    assert starts[0].arguments == {"command": "echo hello"}
    assert len(ends) == 1
    assert "hello" in ends[0].content
    assert ends[0].is_error is False
    assert any(isinstance(event, TextDelta) and event.text == "Done." for event in events)

    step_ends = [event for event in events if isinstance(event, StepEnd)]
    assert len(step_ends) == 2
    assert step_ends[0].usage.input_tokens + step_ends[1].usage.input_tokens == 12

    assert len(requests) == 2
    replay = requests[1]["messages"]
    assert replay[2] == {
        "role": "assistant",
        "content": None,
        "reasoning_content": "Run echo.",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": json.dumps({"command": "echo hello"}),
                },
            }
        ],
    }
    assert replay[3]["role"] == "tool"
    assert replay[3]["tool_call_id"] == "call_1"
    assert "hello" in replay[3]["content"]
    assert history[-1]["content"] == "Done."


def test_max_steps_stops_the_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_stream(_config: Config, _history: list[dict[str, Any]]) -> Iterator[StepEnd]:
        yield step(assistant_tool_call("bash", {"command": "true"}))

    monkeypatch.setattr(agent_module, "stream_step", fake_stream)
    agent = Agent(Config(api_key="test", max_steps=2), str(tmp_path))
    history: list[dict[str, Any]] = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "go"},
    ]

    events = list(agent.run(history))

    assert sum(isinstance(event, ToolStart) for event in events) == 2
    assert any(
        isinstance(event, Notice) and "Step limit (2) reached" in event.text for event in events
    )


def test_unknown_tool_is_reported_to_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"count": 0}

    def fake_stream(_config: Config, _history: list[dict[str, Any]]) -> Iterator[StepEnd]:
        calls["count"] += 1
        if calls["count"] == 1:
            yield step(assistant_tool_call("nope", {}, "call_x"))
        else:
            yield step({"role": "assistant", "content": "done", "reasoning_content": ""})

    monkeypatch.setattr(agent_module, "stream_step", fake_stream)
    agent = Agent(Config(api_key="test", max_steps=3), str(tmp_path))
    history: list[dict[str, Any]] = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "go"},
    ]

    events = list(agent.run(history))

    ends = [event for event in events if isinstance(event, ToolEnd)]
    assert ends[0].is_error is True
    assert "Unknown tool 'nope'" in ends[0].content
    assert history[3]["role"] == "tool"
    assert "Unknown tool" in history[3]["content"]


def test_malformed_json_is_reported_to_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"count": 0}

    def fake_stream(_config: Config, _history: list[dict[str, Any]]) -> Iterator[StepEnd]:
        calls["count"] += 1
        if calls["count"] == 1:
            yield step(assistant_tool_call("bash", "{bad json", "call_bad"))
        else:
            yield step({"role": "assistant", "content": "recovered", "reasoning_content": ""})

    monkeypatch.setattr(agent_module, "stream_step", fake_stream)
    agent = Agent(Config(api_key="test", max_steps=3), str(tmp_path))
    history: list[dict[str, Any]] = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "go"},
    ]

    events = list(agent.run(history))

    ends = [event for event in events if isinstance(event, ToolEnd)]
    assert ends[0].is_error is True
    assert "Invalid JSON" in ends[0].content
    assert history[3]["role"] == "tool"


def test_multiple_tool_calls_run_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_stream(_config: Config, _history: list[dict[str, Any]]) -> Iterator[StepEnd]:
        calls["count"] += 1
        if calls["count"] == 1:
            message = assistant_tool_call("bash", {"command": "echo one"}, "call_1")
            message["tool_calls"].append(
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "bash", "arguments": json.dumps({"command": "echo two"})},
                }
            )
            yield step(message)
        else:
            yield step({"role": "assistant", "content": "all done", "reasoning_content": ""})

    monkeypatch.setattr(agent_module, "stream_step", fake_stream)
    agent = Agent(Config(api_key="test", max_steps=3), str(tmp_path))
    history: list[dict[str, Any]] = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "go"},
    ]

    events = list(agent.run(history))

    ends = [event for event in events if isinstance(event, ToolEnd)]
    assert [event.call_id for event in ends] == ["call_1", "call_2"]
    assert "one" in ends[0].content
    assert "two" in ends[1].content
    assert [message["tool_call_id"] for message in history if message["role"] == "tool"] == [
        "call_1",
        "call_2",
    ]
