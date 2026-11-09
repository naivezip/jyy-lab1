"""Tests for the bash tool contract."""

from __future__ import annotations

import time
from pathlib import Path

from personal_agent.tools.bash import MAX_TOOL_OUTPUT, BashTool


def test_exit_code_stdout_and_stderr(tmp_path: Path) -> None:
    tool = BashTool(str(tmp_path))

    content, is_error = tool.run({"command": "echo out; echo err >&2; exit 3"})

    assert is_error is True
    assert "exit code: 3" in content
    assert "--- stdout ---\nout" in content
    assert "--- stderr ---\nerr" in content


def test_success(tmp_path: Path) -> None:
    tool = BashTool(str(tmp_path))

    content, is_error = tool.run({"command": "echo ok"})

    assert is_error is False
    assert "exit code: 0" in content
    assert "ok" in content


def test_timeout(tmp_path: Path) -> None:
    tool = BashTool(str(tmp_path))
    started = time.monotonic()

    content, is_error = tool.run({"command": "sleep 2", "timeout": 1})

    assert time.monotonic() - started < 2
    assert is_error is True
    assert "timed out" in content


def test_output_is_truncated(tmp_path: Path) -> None:
    tool = BashTool(str(tmp_path))

    content, _ = tool.run({"command": "head -c 20000 /dev/zero | tr '\\0' x"})

    assert "[truncated:" in content
    assert len(content) < MAX_TOOL_OUTPUT + 100


def test_stdin_is_not_taken_from_the_repl(tmp_path: Path) -> None:
    tool = BashTool(str(tmp_path))

    content, _ = tool.run({"command": 'read -r line; echo "read=$?"'})

    assert "read=1" in content


def test_invalid_arguments(tmp_path: Path) -> None:
    tool = BashTool(str(tmp_path))

    content, is_error = tool.run({"command": ""})

    assert is_error is True
    assert "non-empty" in content
