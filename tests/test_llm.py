"""Contract tests for the streaming OpenAI SDK adapter."""

from __future__ import annotations

import json
import time

from personal_agent.config import Config
from personal_agent.llm import Notice, ReasoningDelta, StepEnd, TextDelta, stream_step
from personal_agent.verify.fake_server import DONE, FakeSSEServer, chunk


def make_config(server: FakeSSEServer) -> Config:
    return Config(
        api_key="test-key",
        model="deepseek-flash",
        base_url=server.base_url,
        max_steps=3,
    )


def test_request_contract_and_incremental_streaming() -> None:
    script = [
        (0.0, chunk(delta={"reasoning_content": "Think."})),
        (0.0, chunk(delta={"content": "Hello"})),
        (1.0, chunk(delta={"content": " world"})),
        (
            0.0,
            chunk(
                delta={},
                finish_reason="stop",
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            ),
        ),
        (0.0, DONE),
    ]

    with FakeSSEServer([script]) as server:
        started = time.monotonic()
        events = stream_step(
            make_config(server),
            [{"role": "user", "content": "hi"}],
        )
        first = next(events)
        second = next(events)
        first_text_at = time.monotonic() - started
        rest = list(events)
        request = server.requests[0]

    assert isinstance(first, ReasoningDelta)
    assert first.text == "Think."
    assert isinstance(second, TextDelta)
    assert second.text == "Hello"
    assert first_text_at < 0.8
    assert any(isinstance(event, TextDelta) and event.text == " world" for event in rest)

    end = next(event for event in rest if isinstance(event, StepEnd))
    assert end.message["content"] == "Hello world"
    assert end.message["reasoning_content"] == "Think."
    assert end.usage.input_tokens == 10
    assert end.usage.output_tokens == 5

    assert request["model"] == "deepseek-flash"
    assert request["stream"] is True
    assert request["stream_options"] == {"include_usage": True}
    assert request["reasoning_effort"] == "high"
    assert request["thinking"] == {"type": "enabled"}
    assert request["tools"][0]["function"]["name"] == "bash"
    assert request["messages"] == [{"role": "user", "content": "hi"}]


def test_tool_call_fragments_are_assembled() -> None:
    arguments = json.dumps({"command": "echo hello"})
    script = [
        (0.0, chunk(delta={"reasoning_content": "Use bash."})),
        (
            0.0,
            chunk(
                delta={
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "bash", "arguments": ""},
                        }
                    ]
                }
            ),
        ),
        (
            0.0,
            chunk(delta={"tool_calls": [{"index": 0, "function": {"arguments": arguments[:10]}}]}),
        ),
        (
            0.0,
            chunk(delta={"tool_calls": [{"index": 0, "function": {"arguments": arguments[10:]}}]}),
        ),
        (0.0, chunk(delta={}, finish_reason="tool_calls")),
        (0.0, chunk(usage={"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9})),
        (0.0, DONE),
    ]

    with FakeSSEServer([script]) as server:
        events = list(stream_step(make_config(server), [{"role": "user", "content": "run it"}]))

    end = next(event for event in events if isinstance(event, StepEnd))
    assert end.message["content"] is None
    assert end.message["reasoning_content"] == "Use bash."
    call = end.message["tool_calls"][0]
    assert call["id"] == "call_1"
    assert call["function"]["name"] == "bash"
    assert json.loads(call["function"]["arguments"]) == {"command": "echo hello"}


def test_length_finish_reason_produces_a_notice() -> None:
    script = [
        (0.0, chunk(delta={"content": "partial"})),
        (0.0, chunk(delta={}, finish_reason="length")),
        (0.0, chunk(usage={"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4})),
        (0.0, DONE),
    ]

    with FakeSSEServer([script]) as server:
        events = list(stream_step(make_config(server), [{"role": "user", "content": "long"}]))

    notices = [event for event in events if isinstance(event, Notice)]
    assert any("truncated" in notice.text for notice in notices)
    assert isinstance(events[-1], StepEnd)
