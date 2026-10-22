from __future__ import annotations

import json

from assistant.messages import Message, ThinkingBlock, ToolCall, ToolResult, tool_message


def test_roundtrip_preserves_everything():
    original = Message(
        role="assistant",
        text="I will read the file.",
        thinking=[ThinkingBlock(type="thinking", text="Need the config.", signature="sig123")],
        tool_calls=[ToolCall(id="c1", name="read", arguments={"path": "a.py"})],
    )
    restored = Message.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original


def test_redacted_thinking_roundtrip():
    original = Message(
        role="assistant",
        thinking=[ThinkingBlock(type="redacted_thinking", data="opaque-base64")],
    )
    restored = Message.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored.thinking[0].type == "redacted_thinking"
    assert restored.thinking[0].data == "opaque-base64"
    assert restored.thinking[0].signature is None


def test_visible_only_for_plain_thinking_with_text():
    assert ThinkingBlock(text="hi").visible
    assert not ThinkingBlock(text="").visible
    assert not ThinkingBlock(type="redacted_thinking", data="x").visible


def test_raw_arguments_kept_for_malformed_payloads():
    call = ToolCall(id="c1", name="read", arguments={}, raw_arguments='{"path": ')
    assert call.raw_arguments == '{"path": '
    assert call.arguments == {}


def test_tool_message_holds_parallel_results():
    msg = tool_message([
        ToolResult(tool_call_id="a", content="one"),
        ToolResult(tool_call_id="b", content="two", is_error=True),
    ])
    assert msg.role == "tool"
    assert [r.tool_call_id for r in msg.tool_results] == ["a", "b"]

    restored = Message.from_dict(json.loads(json.dumps(msg.to_dict())))
    assert restored == msg
