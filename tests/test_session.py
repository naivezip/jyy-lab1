from __future__ import annotations

import json

import pytest

from assistant.compact import _tail, compact, is_context_overflow
from assistant.messages import Message, ThinkingBlock, ToolCall, ToolResult, tool_message
from assistant.providers.base import TextDelta, TurnEnd, Usage
from assistant.session import Session


class SummaryProvider:
    name = "fake"

    def __init__(self):
        self.seen = []

    def stream(self, messages, tools):
        self.seen.append(messages)
        yield TextDelta("## Goal\nDo the thing\n## Next step\nFinish")
        yield TurnEnd(Message(role="assistant", text="## Goal\nDo the thing\n## Next step\nFinish"),
                      Usage(10, 5), "end_turn")


def user(text):
    return Message(role="user", text=text)


def test_session_append_is_append_only(tmp_path):
    path = tmp_path / "s.jsonl"
    session = Session(path=path)
    session.append(user("one"))
    session.append(Message(role="assistant", text="two"))

    lines = path.read_text().splitlines()
    assert len(lines) == 2

    loaded = Session.load(path)
    assert [m.text for m in loaded.messages] == ["one", "two"]


def test_compaction_record_roundtrip(tmp_path):
    path = tmp_path / "s.jsonl"
    session = Session(path=path)
    session.append(user("one"))
    session.append_compaction("summary here")
    session.append(user("two"))

    loaded = Session.load(path)
    assert loaded.compactions[0].summary == "summary here"
    assert loaded.compactions[0].replaced_upto == 1
    assert [m.text for m in loaded.messages] == ["one", "two"]


def test_compact_keeps_system_summary_and_tail():
    provider = SummaryProvider()
    history = [Message(role="system", text="sys")]
    for i in range(6):
        history.append(user(f"u{i}"))
        history.append(Message(role="assistant", text=f"a{i}"))

    rebuilt = compact(provider, history)

    assert rebuilt[0].role == "system"
    assert rebuilt[1].role == "user"
    assert "Summary of the earlier conversation" in rebuilt[1].text
    assert len(rebuilt) == 2 + 4
    assert [m.text for m in rebuilt[-2:]] == ["u5", "a5"]


def test_compact_drops_thinking_everywhere():
    provider = SummaryProvider()
    history = [
        user("q"),
        Message(role="assistant", text="a", thinking=[ThinkingBlock(text="secret", signature="s")]),
        user("q2"),
        Message(role="assistant", text="a2"),
        user("q3"),
        Message(role="assistant", text="a3"),
    ]
    rebuilt = compact(provider, history)
    assert all(not m.thinking for m in rebuilt)


def test_transcript_sent_to_summarizer_excludes_thinking():
    provider = SummaryProvider()
    compact(provider, [Message(role="assistant", text="visible",
                               thinking=[ThinkingBlock(text="HIDDEN", signature="s")])])
    sent = provider.seen[0][1].text
    assert "visible" in sent
    assert "HIDDEN" not in sent


def test_tail_never_starts_with_orphan_tool_results():
    messages = [
        user("q"),
        Message(role="assistant", tool_calls=[ToolCall(id="c1", name="read", arguments={})]),
        tool_message([ToolResult(tool_call_id="c1", content="x")]),
        Message(role="assistant", text="done"),
    ]
    tail = _tail(messages, keep=3)
    assert tail[0].role == "assistant"
    assert tail[0].text == "done"


def test_context_overflow_detection():
    assert is_context_overflow(RuntimeError("This model's maximum context length is 8192"))
    assert is_context_overflow(RuntimeError("prompt is too long"))
    assert not is_context_overflow(RuntimeError("invalid api key"))
