from __future__ import annotations

from assistant.config import Config
from assistant.messages import Message
from assistant.render import Renderer
from assistant.session import Session


def make_config(**kw):
    base = dict(
        provider="openai", api_key="k", base_url=None, model="m",
        max_tokens=100, max_steps=5, context_window=1000, show_usage=True,
    )
    base.update(kw)
    return Config(**base)


def test_cli_parser_flags():
    from assistant.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["-c"])
    assert args.resume is True
    args = parser.parse_args(["-p", "hello"])
    assert args.prompt == "hello"
    args = parser.parse_args(["--provider", "anthropic"])
    assert args.provider == "anthropic"


class SinkRenderer(Renderer):
    def __init__(self):
        import io

        super().__init__(out=io.StringIO(), color=False, show_usage=True)


def test_renderer_groups_thinking_and_text():
    r = SinkRenderer()
    from assistant.providers.base import ThinkingDelta, TextDelta, TurnEnd, Usage

    r.handle(ThinkingDelta("hmm"))
    r.handle(TextDelta("answer"))
    r.handle(TurnEnd(message=None, usage=Usage(1200, 30), stop_reason="stop"))
    r.usage(Usage(1200, 30))
    out = r.out.getvalue()
    assert "✻ hmm" in out
    assert "answer" in out
    assert "1.2k in / 30 out" in out


def test_renderer_marks_tool_errors():
    r = SinkRenderer()
    from assistant.messages import ToolCall, ToolResult
    from assistant.providers.base import ToolEnd, ToolStart

    call = ToolCall(id="c1", name="bash", arguments={"command": "false"})
    r.handle(ToolStart(call))
    r.handle(ToolEnd(call, ToolResult(tool_call_id="c1", content="boom: failed", is_error=True)))
    assert "⏺ bash(command='false')" in r.out.getvalue()
    assert "boom: failed" in r.out.getvalue()


def test_app_rebuilds_tool_outputs_from_resumed_session(tmp_path):
    from assistant.cli import App
    from assistant.messages import Message, ToolResult, tool_message

    session = Session(path=tmp_path / "s.jsonl")
    session.append(Message(role="user", text="q"))
    session.append(tool_message([ToolResult(tool_call_id="c1", content="old output")]))

    app = App.__new__(App)  # skip provider construction (no network)
    app.history = [Message(role="system", text="sys")] + session.active_messages()
    app.tool_outputs = []
    for message in app.history:
        app.tool_outputs.extend(message.tool_results)
    assert app.tool_outputs[0].content == "old output"


def test_compacted_session_resumes_from_summary(tmp_path):
    session = Session(path=tmp_path / "s.jsonl")
    session.append(Message(role="user", text="old question"))
    session.append(Message(role="assistant", text="old answer"))
    session.append_compaction("the summary")
    session.append(Message(role="user", text="new question"))

    active = session.active_messages()
    assert active[0].role == "user"
    assert "the summary" in active[0].text
    assert [m.text for m in active[1:]] == ["new question"]
