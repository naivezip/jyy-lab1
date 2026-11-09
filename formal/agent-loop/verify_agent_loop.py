"""Bounded exhaustive verification of Agent.run history integrity.

Enumerates every sequence of up to MAX_STEPS_TESTED model responses drawn from
the structural response kinds below and runs the real Agent loop for each.
"""

from __future__ import annotations

import itertools
import json
import tempfile
from collections.abc import Iterator
from typing import Any

import personal_agent.agent as agent_module
from personal_agent.agent import Agent
from personal_agent.config import Config
from personal_agent.llm import Notice, StepEnd, Usage

MAX_STEPS_TESTED = 3
RESPONSE_KINDS = ("final", "one-valid", "two-valid", "unknown-tool", "bad-json")


def _tool_call(call_id: str, name: str, arguments: Any) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
        },
    }


def _response(kind: str, step: int) -> dict[str, Any]:
    if kind == "final":
        return {"role": "assistant", "content": "done", "reasoning_content": ""}
    if kind == "one-valid":
        calls = [_tool_call(f"call_{step}_1", "bash", {"command": "true"})]
    elif kind == "two-valid":
        calls = [
            _tool_call(f"call_{step}_1", "bash", {"command": "true"}),
            _tool_call(f"call_{step}_2", "bash", {"command": "true"}),
        ]
    elif kind == "unknown-tool":
        calls = [_tool_call(f"call_{step}_1", "nope", {})]
    elif kind == "bad-json":
        calls = [_tool_call(f"call_{step}_1", "bash", "{bad json")]
    else:
        raise AssertionError(f"unknown response kind {kind!r}")
    return {
        "role": "assistant",
        "content": None,
        "reasoning_content": "",
        "tool_calls": calls,
    }


def _check_history(history: list[dict[str, Any]], max_steps: int) -> None:
    assert history[0]["role"] == "system"
    assert history[1]["role"] == "user"
    index = 2
    assistant_count = 0
    while index < len(history):
        message = history[index]
        assert message["role"] == "assistant", ("expected assistant message", history)
        assistant_count += 1
        calls = message.get("tool_calls") or []
        for call in calls:
            index += 1
            assert index < len(history), ("missing tool message", history)
            tool = history[index]
            assert tool["role"] == "tool", ("orphan message after tool call", history)
            assert tool["tool_call_id"] == call["id"], ("tool id mismatch", history)
            assert isinstance(tool["content"], str)
        index += 1
    assert assistant_count <= max_steps, ("step limit exceeded", history)


def _check_end_state(history: list[dict[str, Any]], events: list[Any], max_steps: int) -> None:
    assistant_messages = [message for message in history if message["role"] == "assistant"]
    last = assistant_messages[-1]
    last_calls = last.get("tool_calls") or []
    notice = any(isinstance(event, Notice) and "Step limit" in event.text for event in events)
    if len(assistant_messages) == max_steps and last_calls:
        assert notice, ("expected step-limit notice", history)
    else:
        assert not last_calls, ("turn stopped after an unanswered tool call", history)
        assert not notice, ("unexpected step-limit notice", history)


def _run(script: tuple[str, ...], max_steps: int, cwd: str) -> list[Any]:
    history: list[dict[str, Any]] = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "go"},
    ]
    calls = {"count": 0}

    def fake_stream(_config: Config, current: list[dict[str, Any]]) -> Iterator[StepEnd]:
        _check_history(current, max_steps)
        index = calls["count"]
        calls["count"] += 1
        if index >= len(script):
            raise AssertionError(
                f"Agent requested model step {index + 1} but the script has {len(script)}"
            )
        yield StepEnd(
            message=_response(script[index], index),
            usage=Usage(),
            finish_reason=None,
        )

    agent = Agent(Config(api_key="test", max_steps=max_steps), cwd)
    original = agent_module.stream_step
    agent_module.stream_step = fake_stream
    try:
        events = list(agent.run(history))
    finally:
        agent_module.stream_step = original

    assert calls["count"] <= max_steps, ("model called too often", script, calls)
    _check_history(history, max_steps)
    _check_end_state(history, events, max_steps)
    return events


def verify() -> int:
    checked = 0
    with tempfile.TemporaryDirectory() as cwd:
        for max_steps in range(1, MAX_STEPS_TESTED + 1):
            for script in itertools.product(RESPONSE_KINDS, repeat=max_steps):
                _run(script, max_steps, cwd)
                checked += 1
    print(f"verified {checked} response sequences (max_steps 1..{MAX_STEPS_TESTED})")
    return 0


if __name__ == "__main__":
    raise SystemExit(verify())
