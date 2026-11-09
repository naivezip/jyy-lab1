"""CLI acceptance tests: subprocess and PTY."""

from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
import time
from pathlib import Path

from personal_agent.verify.fake_server import DONE, FakeSSEServer, chunk

ROOT = Path(__file__).resolve().parents[1]


def cli_environment(server: FakeSSEServer | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PA_API_KEY": "test-key",
            "PA_MODEL": "deepseek-flash",
            "PA_MAX_STEPS": "5",
            "PYTHONPATH": str(ROOT / "src"),
        }
    )
    if server is not None:
        env["PA_BASE_URL"] = server.base_url
    return env


def run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "personal_agent", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class PtyReader:
    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._buffer = b""

    def read_until(self, needle: bytes, timeout: float = 10.0) -> bytes:
        deadline = time.monotonic() + timeout
        while needle not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(
                    f"Timed out waiting for {needle!r}; output so far: {self._buffer!r}"
                )
            ready, _, _ = select.select([self._fd], [], [], min(0.1, remaining))
            if not ready:
                continue
            try:
                piece = os.read(self._fd, 4096)
            except OSError:
                break
            if not piece:
                break
            self._buffer += piece

        index = self._buffer.index(needle) + len(needle)
        data, self._buffer = self._buffer[:index], self._buffer[index:]
        return data


def text_script(text: str) -> list[tuple[float, dict[str, object] | str]]:
    return [
        (0.0, chunk(delta={"content": text})),
        (0.0, chunk(delta={}, finish_reason="stop")),
        (0.0, chunk(usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})),
        (0.0, DONE),
    ]


def test_version_exits_zero() -> None:
    result = run_cli(["--version"], cli_environment())

    assert result.returncode == 0
    assert "pa 0.1.0" in result.stdout


def test_help_exits_zero() -> None:
    result = run_cli(["--help"], cli_environment())

    assert result.returncode == 0
    assert "usage: pa" in result.stdout


def test_missing_api_key_is_a_config_error() -> None:
    env = cli_environment()
    env.pop("PA_API_KEY", None)

    result = run_cli(["-p", "hi"], env)

    assert result.returncode == 2
    assert "PA_API_KEY" in result.stderr


def test_one_shot_streams_and_prints_usage() -> None:
    with FakeSSEServer([text_script("Hello CLI")]) as server:
        result = run_cli(["-p", "hi"], cli_environment(server))
        requests = server.requests

    assert result.returncode == 0
    assert "Hello CLI" in result.stdout
    assert "[tokens] input=10 output=2" in result.stdout
    assert requests[0]["messages"][0]["role"] == "system"
    assert requests[0]["messages"][1] == {"role": "user", "content": "hi"}


def test_repl_streams_a_turn_and_handles_commands() -> None:
    with FakeSSEServer([text_script("Hello REPL")]) as server:
        master, slave = pty.openpty()
        process = subprocess.Popen(
            [sys.executable, "-m", "personal_agent"],
            cwd=ROOT,
            env=cli_environment(server),
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
        )
        os.close(slave)
        reader = PtyReader(master)
        try:
            output = reader.read_until(b"Type /help for commands.")
            os.write(master, b"/help\n")
            output += reader.read_until(b"Commands:")
            os.write(master, b"hello\n")
            output += reader.read_until(b"Hello REPL")
            output += reader.read_until(b"[tokens]")
            os.write(master, b"/new\n")
            output += reader.read_until(b"New conversation.")
            os.write(master, b"/exit\n")
            process.wait(timeout=10)
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    assert process.returncode == 0
    assert b"Hello REPL" in output
    assert b"[tokens] input=10 output=2" in output
    assert b"New conversation." in output
