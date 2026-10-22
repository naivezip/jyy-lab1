"""The `pa` command: interactive REPL, one-shot mode, session resumption."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from assistant import __version__
from assistant.agent import Agent
from assistant.compact import compact, estimate_overflow
from assistant.config import Config, ConfigError, load_config
from assistant.context import build_system_prompt
from assistant.messages import Message, ToolResult, tool_message
from assistant.net import sanitize_proxy_env
from assistant.providers import build_provider
from assistant.providers.base import Notice, ProviderError
from assistant.render import Renderer, show_pager
from assistant.session import Session, latest_session, list_sessions
from assistant.tools import default_registry

HELP = """\
Commands:
  /help              show this help
  /new               start a new session
  /sessions          list sessions for this directory
  /compact           summarise the conversation and free context
  /show [n]          open the n-th most recent tool output (default: latest)
  /exit              leave (Ctrl-D also works)
"""

SUMMARY_PREFIX = "Summary of the earlier conversation:\n\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pa", description="A local personal assistant with tools."
    )
    parser.add_argument(
        "-c", "--continue", dest="resume", action="store_true",
        help="resume the most recent session in this directory",
    )
    parser.add_argument(
        "-p", "--print", dest="prompt", metavar="PROMPT",
        help="run one prompt and exit",
    )
    parser.add_argument(
        "--provider", choices=("openai", "anthropic"),
        help="override PA_PROVIDER for this run",
    )
    parser.add_argument("--version", action="version", version=f"pa {__version__}")
    return parser


class App:
    def __init__(self, config: Config, cwd: str, session: Session | None = None) -> None:
        self.config = config
        self.cwd = cwd
        self.provider = build_provider(config)
        self.registry = default_registry(cwd)
        self.renderer = Renderer(show_usage=config.show_usage)
        self.session = session or Session.create(cwd)
        self.tool_outputs: list[ToolResult] = []

        self.history: list[Message] = [
            Message(role="system", text=build_system_prompt(cwd))
        ]
        if session is not None:
            self.history.extend(session.active_messages())
            for message in self.history:
                self.tool_outputs.extend(message.tool_results)
        # Identity, not equality: two identical user messages are both real.
        self._persisted: set[int] = set()

    def ask(self, text: str) -> None:
        user_message = Message(role="user", text=text)
        self.history.append(user_message)
        self.session.append(user_message)
        self._persisted.add(id(user_message))

        agent = Agent(
            self.provider,
            self.registry,
            max_steps=self.config.max_steps,
            on_event=self._on_event,
        )
        pending = len(self.history) - 1
        try:
            result = agent.run(self.history)
        except ProviderError as exc:
            self.renderer.handle(Notice(f"Request failed: {exc}"))
            return
        except KeyboardInterrupt:
            # A partial assistant stream is never in history, but a completed
            # assistant tool-call message can be; close it so the next request
            # does not send orphaned tool calls.
            self._close_dangling_tool_calls()
            self.renderer.handle(Notice("Interrupted."))
            return
        finally:
            self._persist_from(pending)

        self.renderer.usage(result.usage)
        self._maybe_auto_compact(result.context_tokens)

    def _close_dangling_tool_calls(self) -> None:
        if not self.history:
            return
        last = self.history[-1]
        if last.role == "assistant" and last.tool_calls:
            completed = set()
            if len(self.history) >= 2 and self.history[-2].role == "tool":
                completed = {r.tool_call_id for r in self.history[-2].tool_results}
            missing = [c for c in last.tool_calls if c.id not in completed]
            if missing:
                self.history.append(tool_message([
                    ToolResult(tool_call_id=c.id, content="Interrupted by user.", is_error=True)
                    for c in missing
                ]))

    def _on_event(self, event) -> None:
        self.renderer.handle(event)
        if hasattr(event, "result"):
            self.tool_outputs.append(event.result)

    def _persist_from(self, start: int) -> None:
        for message in self.history[start:]:
            if id(message) not in self._persisted:
                self.session.append(message)
                self._persisted.add(id(message))

    def _maybe_auto_compact(self, input_tokens: int) -> None:
        if estimate_overflow(input_tokens, self.config.context_window):
            self.compact_history(reason="context is filling up")

    def compact_history(self, reason: str = "") -> None:
        suffix = f" ({reason})" if reason else ""
        self.renderer.handle(Notice(f"Compacting conversation{suffix}..."))
        try:
            rebuilt = compact(self.provider, self.history)
        except ProviderError as exc:
            self.renderer.handle(Notice(f"Compaction failed: {exc}"))
            return
        summary = rebuilt[1].text or ""
        if summary.startswith(SUMMARY_PREFIX):
            summary = summary[len(SUMMARY_PREFIX):]
        self.history = rebuilt
        self.session.append_compaction(summary.strip(), {id(m) for m in rebuilt})
        self.renderer.handle(Notice("Conversation compacted."))

    def handle_command(self, line: str) -> bool:
        command, _, argument = line.partition(" ")
        if command == "/help":
            print(HELP)
        elif command == "/exit":
            return False
        elif command == "/new":
            self.session = Session.create(self.cwd)
            self.history = [self.history[0]]
            self.tool_outputs.clear()
            print(f"New session: {self.session.path.name}")
        elif command == "/sessions":
            for path in list_sessions(self.cwd)[:20]:
                marker = "*" if path == self.session.path else " "
                print(f"{marker} {path.name}")
        elif command == "/compact":
            self.compact_history()
        elif command == "/show":
            self.show_output(argument.strip())
        else:
            print(f"Unknown command: {command}. Try /help.")
        return True

    def show_output(self, argument: str) -> None:
        if not self.tool_outputs:
            print("No tool output in this session yet.")
            return
        try:
            index = int(argument) if argument else 1
        except ValueError:
            print("Usage: /show [n]")
            return
        if index < 1 or index > len(self.tool_outputs):
            print(f"Only {len(self.tool_outputs)} tool outputs available.")
            return
        show_pager(self.tool_outputs[-index].content)


def run_repl(app: App) -> int:
    print(f"pa {__version__} · {app.config.provider}/{app.config.model} · {app.cwd}")
    print(f"Session: {app.session.path.name} · /help for commands")
    while True:
        try:
            line = input("\n› ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        line = line.strip()
        if not line:
            continue
        if line.startswith("/"):
            if not app.handle_command(line):
                return 0
            continue
        try:
            app.ask(line)
        except KeyboardInterrupt:
            print("\n[interrupted]")
    return 0


def main(argv: list[str] | None = None) -> int:
    sanitize_proxy_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    cwd = str(Path.cwd())

    try:
        config = load_config(args.provider)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    session = None
    if args.resume:
        path = latest_session(cwd)
        if path is None:
            print("No previous session in this directory; starting a new one.", file=sys.stderr)
        else:
            session = Session.load(path)
            print(f"Resumed {path.name} ({len(session.messages)} messages)")

    app = App(config, cwd, session=session)

    if args.prompt:
        app.ask(args.prompt)
        return 0
    return run_repl(app)


if __name__ == "__main__":
    raise SystemExit(main())
