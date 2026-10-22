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


class DummyProvider:
    name = "fake"

    def __init__(self):
        self.requests = []

    def stream(self, messages, tools):
        from assistant.providers.base import TextDelta, TurnEnd, Usage

        self.requests.append((list(messages), [t.name for t in tools]))
        if tools:
            yield TextDelta("ok")
            yield TurnEnd(Message(role="assistant", text="ok"), Usage(1, 1), "stop")
        else:
            summary = "## Goal\nsummarise"
            yield TextDelta(summary)
            yield TurnEnd(Message(role="assistant", text=summary), Usage(2, 2), "stop")


def make_app(tmp_path):
    from assistant.cli import App
    from assistant.render import Renderer
    from assistant.session import Session
    from assistant.tools import default_registry
    import io

    app = App.__new__(App)
    app.config = make_config()
    app.cwd = str(tmp_path)
    app.provider = DummyProvider()
    app.registry = default_registry(str(tmp_path))
    app.renderer = Renderer(out=io.StringIO(), color=False, show_usage=False)
    app.session = Session(path=tmp_path / "s.jsonl")
    app.history = [Message(role="system", text="sys")]
    app.tool_outputs = []
    app._persisted = set()
    return app


def test_compact_command_writes_record_and_rebuilds_history(tmp_path):
    app = make_app(tmp_path)
    app.ask("hello")
    before = len(app.session.messages)

    app.handle_command("/compact")

    # system + summary + the verbatim tail (the whole short conversation fits)
    assert app.history[0].role == "system"
    assert app.history[1].text.startswith("Summary of the earlier conversation")
    assert [m.text for m in app.history[2:]] == ["hello", "ok"]
    assert app.session.compactions[-1].summary == "## Goal\nsummarise"
    assert len(app.session.path.read_text().splitlines()) == before + 1


def test_show_uses_most_recent_by_default(tmp_path):
    from assistant.messages import ToolResult

    app = make_app(tmp_path)
    app.tool_outputs = [
        ToolResult(tool_call_id="a", content="older"),
        ToolResult(tool_call_id="b", content="newer"),
    ]
    captured = {}
    import assistant.cli as cli

    original = cli.show_pager
    cli.show_pager = lambda text: captured.__setitem__("text", text)
    try:
        app.handle_command("/show")
        assert captured["text"] == "newer"
        app.handle_command("/show 2")
        assert captured["text"] == "older"
    finally:
        cli.show_pager = original


def test_show_rejects_out_of_range(tmp_path, capsys):
    app = make_app(tmp_path)
    app.handle_command("/show")
    assert "No tool output" in capsys.readouterr().out


def test_interrupt_closes_dangling_tool_calls(tmp_path):
    from assistant.messages import ToolCall, ToolResult, tool_message

    app = make_app(tmp_path)
    app.history.append(Message(role="user", text="q"))
    app.history.append(Message(
        role="assistant", thinking=[],
        tool_calls=[
            ToolCall(id="c1", name="read", arguments={}),
            ToolCall(id="c2", name="read", arguments={}),
        ],
    ))
    app.history.append(tool_message([ToolResult(tool_call_id="c1", content="done")]))

    app._close_dangling_tool_calls()

    assert app.history[-1].role == "tool"
    assert app.history[-1].tool_results[0].tool_call_id == "c2"
    assert app.history[-1].tool_results[0].is_error
