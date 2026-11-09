"""The `pa` command: streaming REPL and one-shot mode."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, TextIO

from . import __version__
from .agent import Agent, ToolEnd, ToolStart
from .config import Config, ConfigError, load_config
from .llm import LLMError, Notice, ReasoningDelta, StepEnd, TextDelta, Usage
from .prompt import build_system_prompt

HELP = """\
Commands:
  /help  show this help
  /new   clear the conversation
  /exit  leave (Ctrl-D also works)
"""


class Renderer:
    """Write streamed events to the terminal."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout
        self._color = self._stream.isatty()
        self._reasoning = False
        self._line_open = False

    def text(self, text: str) -> None:
        if self._reasoning:
            self._close_reasoning()
        self._write(text)
        self._line_open = not text.endswith("\n")

    def reasoning(self, text: str) -> None:
        if not self._reasoning:
            if self._line_open:
                self._write("\n")
            if self._color:
                self._write("\x1b[2m")
            self._reasoning = True
        self._write(text)
        self._line_open = not text.endswith("\n")

    def notice(self, text: str) -> None:
        self._end_line()
        self._dim(f"[{text}]\n")

    def tool_start(self, event: ToolStart) -> None:
        self._end_line()
        command = event.arguments.get("command", "")
        self._dim(f"$ {command}\n")

    def tool_end(self, event: ToolEnd) -> None:
        first_line = event.content.splitlines()[0] if event.content else "no output"
        self._dim(f"[{event.name}: {first_line}]\n")

    def step_end(self, _event: StepEnd) -> None:
        self._end_line()

    def usage(self, usage: Usage) -> None:
        self._end_line()
        self._dim(f"[tokens] input={usage.input_tokens} output={usage.output_tokens}\n")

    def end_turn(self) -> None:
        self._end_line()

    def _close_reasoning(self) -> None:
        if self._color:
            self._write("\x1b[0m")
        if self._line_open:
            self._write("\n")
        self._reasoning = False
        self._line_open = False

    def _end_line(self) -> None:
        if self._reasoning:
            self._close_reasoning()
        elif self._line_open:
            self._write("\n")
            self._line_open = False

    def _dim(self, text: str) -> None:
        if self._color:
            self._write(f"\x1b[2m{text}\x1b[0m")
        else:
            self._write(text)

    def _write(self, text: str) -> None:
        self._stream.write(text)
        self._stream.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pa",
        description="A personal agent for the terminal.",
    )
    parser.add_argument(
        "-p",
        "--print",
        dest="prompt",
        metavar="TEXT",
        help="run one prompt and exit",
    )
    parser.add_argument(
        "--model",
        help="override PA_MODEL for this run",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"pa {__version__}",
    )
    return parser


def run_turn(
    agent: Agent,
    history: list[dict[str, Any]],
    text: str,
    renderer: Renderer,
) -> bool:
    """Run one user turn. Return False when the turn failed."""
    start = len(history)
    history.append({"role": "user", "content": text})
    usage = Usage()

    try:
        for event in agent.run(history):
            if isinstance(event, TextDelta):
                renderer.text(event.text)
            elif isinstance(event, ReasoningDelta):
                renderer.reasoning(event.text)
            elif isinstance(event, Notice):
                renderer.notice(event.text)
            elif isinstance(event, ToolStart):
                renderer.tool_start(event)
            elif isinstance(event, ToolEnd):
                renderer.tool_end(event)
            elif isinstance(event, StepEnd):
                renderer.step_end(event)
                usage = usage + event.usage
    except LLMError as exc:
        renderer.end_turn()
        del history[start:]
        print(f"error: {exc}", file=sys.stderr)
        return False
    except KeyboardInterrupt:
        renderer.end_turn()
        del history[start:]
        print("\n[interrupted]", file=sys.stderr)
        return False

    renderer.usage(usage)
    return True


def handle_command(line: str, history: list[dict[str, Any]]) -> bool:
    command, _, _argument = line.partition(" ")
    if command == "/help":
        print(HELP)
    elif command == "/new":
        del history[1:]
        print("New conversation.")
    elif command == "/exit":
        return False
    else:
        print(f"Unknown command: {command}. Try /help.")
    return True


def run_repl(agent: Agent, history: list[dict[str, Any]], config: Config) -> int:
    renderer = Renderer()
    print(f"pa {__version__} | {config.model} | {Path.cwd()}")
    print("Type /help for commands.")

    while True:
        try:
            line = input("\n> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            continue

        line = line.strip()
        if not line:
            continue
        if line.startswith("/"):
            if not handle_command(line, history):
                return 0
            continue

        try:
            run_turn(agent, history, line, renderer)
        except KeyboardInterrupt:
            print("\n[interrupted]", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.model)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    cwd = str(Path.cwd())
    agent = Agent(config, cwd)
    history: list[dict[str, Any]] = [{"role": "system", "content": build_system_prompt(cwd)}]

    if args.prompt is not None:
        return 0 if run_turn(agent, history, args.prompt, Renderer()) else 1
    return run_repl(agent, history, config)


if __name__ == "__main__":
    raise SystemExit(main())
