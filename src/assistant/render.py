"""Terminal rendering for stream events."""

from __future__ import annotations

import os
import sys
from typing import TextIO

from assistant.messages import ToolCall
from assistant.providers.base import (
    Notice,
    TextDelta,
    ThinkingDelta,
    ToolEnd,
    ToolStart,
    TurnEnd,
    Usage,
)

RESET = "\x1b[0m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
CYAN = "\x1b[36m"
YELLOW = "\x1b[33m"


class Renderer:
    """Streams model output to a terminal; redraws status lines per turn."""

    def __init__(self, out: TextIO | None = None, color: bool | None = None,
                 show_usage: bool = True) -> None:
        self.out = out or sys.stdout
        self.color = (self.out.isatty() if color is None else color)
        self.show_usage = show_usage
        self._thinking_open = False
        self._text_open = False
        self._any_output = False

    def _style(self, code: str, text: str) -> str:
        return f"{code}{text}{RESET}" if self.color else text

    def _close_thinking(self) -> None:
        if self._thinking_open:
            self._write("\n")
            self._thinking_open = False

    def _write(self, text: str) -> None:
        self.out.write(text)
        self.out.flush()

    def handle(self, event) -> None:
        if isinstance(event, ThinkingDelta):
            if not self._thinking_open:
                self._close_text()
                self._write(self._style(DIM, "✻ "))
                self._thinking_open = True
            self._write(self._style(DIM, event.text))
            self._any_output = True
        elif isinstance(event, TextDelta):
            self._close_thinking()
            if not self._text_open:
                self._text_open = True
            self._write(event.text)
            self._any_output = True
        elif isinstance(event, ToolStart):
            self._close_all()
            self._write(self._style(CYAN, f"⏺ {event.call.name}") + self._format_args(event.call) + "\n")
            self._any_output = True
        elif isinstance(event, ToolEnd):
            summary = _summarize(event.result.content, event.result.is_error)
            color = RED if event.result.is_error else GREEN
            self._write(self._style(color, f"  ⎿ {summary}") + "\n")
        elif isinstance(event, Notice):
            self._close_all()
            self._write(self._style(YELLOW, f"! {event.text}") + "\n")
        elif isinstance(event, TurnEnd):
            self._close_all()
            if self.show_usage and (event.usage.input_tokens or event.usage.output_tokens):
                self._write(
                    self._style(DIM, f"[{_tokens(event.usage.input_tokens)} in / "
                                     f"{_tokens(event.usage.output_tokens)} out]") + "\n"
                )

    def _close_text(self) -> None:
        if self._text_open:
            self._text_open = False

    def _close_all(self) -> None:
        self._close_thinking()
        if self._text_open:
            self._write("\n")
            self._text_open = False
        self._any_output = False

    @staticmethod
    def _format_args(call: ToolCall) -> str:
        args = ", ".join(f"{key}={value!r}" for key, value in call.arguments.items())
        return f"({args})" if args else "()"


def _tokens(count: int) -> str:
    if count >= 1000:
        return f"{count / 1000:.1f}k"
    return str(count)


def _summarize(content: str, is_error: bool) -> str:
    first = content.strip().splitlines()[0] if content.strip() else ""
    if is_error:
        return first[:120] or "error"
    lines = len(content.splitlines())
    return f"{lines} line{'s' if lines != 1 else ''}"


def show_pager(text: str) -> None:
    """Open text in $PAGER (default less), falling back to plain printing."""
    pager = os.environ.get("PAGER", "less")
    if not sys.stdout.isatty() or not pager:
        print(text)
        return
    import subprocess

    try:
        subprocess.run([pager], input=text, text=True, check=False)
    except (OSError, ValueError):
        print(text)
