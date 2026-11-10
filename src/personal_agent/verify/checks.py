"""Black-box acceptance checks driven through the real `pa` CLI."""

from __future__ import annotations

import json
import os
import pty
import select
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .fake_server import DONE, FakeSSEServer, SSEEvent, chunk

Status = Literal["pass", "fail"]

_PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
_UNREACHABLE_BASE_URL = "http://127.0.0.1:9/v1"
_OUTPUT_TAIL = 400


@dataclass(frozen=True)
class Evidence:
    """One observed fact recorded while a check runs."""

    label: str
    value: str


@dataclass(frozen=True)
class Check:
    """One acceptance criterion and the session method that proves it."""

    id: str
    criterion: int
    title: str
    run: Callable[[VerificationSession], None]


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check, including evidence gathered before a failure."""

    check: Check
    duration_ms: int
    evidence: tuple[Evidence, ...]
    failure: str | None = None

    @property
    def status(self) -> Status:
        return "fail" if self.failure is not None else "pass"


@dataclass(frozen=True)
class Report:
    """All selected results plus the wall-clock duration of the run."""

    results: tuple[CheckResult, ...]
    duration_ms: int

    @property
    def ok(self) -> bool:
        return all(result.status == "pass" for result in self.results)


@dataclass(frozen=True)
class CliResult:
    """The observed end state of one completed CLI process."""

    returncode: int
    output: str


class CheckFailed(Exception):
    """A check observed a value that violates its acceptance criterion."""


class CliProcess:
    """A live `python -m personal_agent` child with pipe or PTY reads."""

    def __init__(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        terminal: bool,
        timeout: float,
    ) -> None:
        self._argv = list(argv)
        self._cwd = cwd
        self._env = dict(env)
        self._terminal = terminal
        self._timeout = timeout
        self._process: subprocess.Popen[bytes] | None = None
        self._master_fd: int | None = None
        self._read_fd: int | None = None
        self._buffer = b""
        self._eof = False

    def __enter__(self) -> CliProcess:
        if self._terminal:
            master, slave = pty.openpty()
            try:
                self._process = subprocess.Popen(
                    self._argv,
                    cwd=self._cwd,
                    env=self._env,
                    stdin=slave,
                    stdout=slave,
                    stderr=slave,
                    close_fds=True,
                )
            except Exception:
                os.close(master)
                os.close(slave)
                raise
            os.close(slave)
            self._master_fd = master
            self._read_fd = master
        else:
            process = subprocess.Popen(
                self._argv,
                cwd=self._cwd,
                env=self._env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
            )
            self._process = process
            assert process.stdout is not None
            self._read_fd = process.stdout.fileno()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        if process is not None and process.stdout is not None:
            process.stdout.close()
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
        self._process = None
        self._master_fd = None
        self._read_fd = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def read_until(self, needle: str | bytes, timeout: float | None = None) -> str | bytes:
        as_text = isinstance(needle, str)
        marker = needle.encode() if as_text else needle
        deadline = time.monotonic() + (self._timeout if timeout is None else timeout)
        while marker not in self._buffer:
            if self._eof:
                raise TimeoutError(f"output ended before {needle!r}; got {self._tail()!r}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for {needle!r}; got {self._tail()!r}")
            self._read_once(min(0.1, remaining))
        index = self._buffer.index(marker) + len(marker)
        data, self._buffer = self._buffer[:index], self._buffer[index:]
        return data.decode("utf-8", errors="replace") if as_text else data

    def read_all(self, timeout: float | None = None) -> str:
        deadline = time.monotonic() + (self._timeout if timeout is None else timeout)
        chunks = [self._buffer]
        self._buffer = b""
        while not self._eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                text = b"".join(chunks).decode("utf-8", errors="replace")
                raise TimeoutError(f"timed out reading output; got {text[-_OUTPUT_TAIL:]!r}")
            self._read_once(min(0.1, remaining))
            if self._buffer:
                chunks.append(self._buffer)
                self._buffer = b""
        return b"".join(chunks).decode("utf-8", errors="replace")

    def send(self, text: str | bytes) -> None:
        if self._master_fd is None:
            raise RuntimeError("send() requires a terminal process")
        payload = text.encode() if isinstance(text, str) else text
        os.write(self._master_fd, payload)

    def wait(self, timeout: float | None = None) -> int:
        if self._process is None:
            raise RuntimeError("process has not been started")
        wait_timeout = self._timeout if timeout is None else timeout
        try:
            return self._process.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"process did not exit within {wait_timeout}s") from exc

    def _read_once(self, timeout: float) -> None:
        if self._read_fd is None:
            self._eof = True
            return
        ready, _, _ = select.select([self._read_fd], [], [], timeout)
        if not ready:
            return
        try:
            piece = os.read(self._read_fd, 4096)
        except OSError:
            self._eof = True
            return
        if not piece:
            self._eof = True
            return
        self._buffer += piece

    def _tail(self) -> str:
        return self._buffer[-_OUTPUT_TAIL:].decode("utf-8", errors="replace")


class VerificationSession:
    """Own every resource a check can touch and every fact a report can show."""

    def __init__(
        self,
        *,
        python: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._python = python or sys.executable
        self._timeout = timeout
        self._tmp = tempfile.TemporaryDirectory(prefix="pa-verify-")
        self._root = Path(self._tmp.name)
        self._evidence: list[Evidence] = []

    def __enter__(self) -> VerificationSession:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self._tmp.cleanup()

    def run(self, check: Check) -> CheckResult:
        self._evidence = []
        started = time.monotonic()
        failure: str | None = None
        try:
            check.run(self)
        except CheckFailed as exc:
            failure = str(exc)
        except TimeoutError as exc:
            failure = f"timeout: {exc}"
        except Exception as exc:  # noqa: BLE001 - one broken check must not abort the rest
            failure = f"internal error: {type(exc).__name__}: {exc}"
        duration_ms = round((time.monotonic() - started) * 1000)
        return CheckResult(
            check=check,
            duration_ms=duration_ms,
            evidence=tuple(self._evidence),
            failure=failure,
        )

    def run_all(self, checks: Sequence[Check]) -> tuple[CheckResult, ...]:
        return tuple(self.run(check) for check in checks)

    def note(self, label: str, value: object) -> None:
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        self._evidence.append(Evidence(label=label, value=text))

    def expect(self, condition: bool, message: str) -> None:
        if not condition:
            raise CheckFailed(message)

    def expect_equal(self, label: str, actual: object, expected: object) -> None:
        if actual != expected:
            raise CheckFailed(f"{label}: expected {_short(expected)}, got {_short(actual)}")

    def expect_in(self, needle: str, haystack: str, label: str) -> None:
        if needle not in haystack:
            raise CheckFailed(
                f"{label}: expected to find {needle!r}, got {haystack[-_OUTPUT_TAIL:]!r}"
            )

    @contextmanager
    def workspace(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(dir=self._root) as name:
            yield Path(name)

    @contextmanager
    def fake_server(self, scripts: Sequence[Sequence[SSEEvent]]) -> Iterator[FakeSSEServer]:
        server = FakeSSEServer([list(script) for script in scripts])
        server.start()
        try:
            yield server
        finally:
            server.stop()

    @contextmanager
    def launch_cli(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        server: FakeSSEServer | None = None,
        terminal: bool = False,
    ) -> Iterator[CliProcess]:
        process = CliProcess(
            [self._python, "-m", "personal_agent", *args],
            cwd=cwd,
            env=self._child_env(server),
            terminal=terminal,
            timeout=self._timeout,
        )
        with process:
            yield process

    def run_cli(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        server: FakeSSEServer | None = None,
    ) -> CliResult:
        with self.launch_cli(args, cwd=cwd, server=server) as process:
            output = process.read_all(self._timeout)
            returncode = process.wait(self._timeout)
        return CliResult(returncode=returncode, output=output)

    def _child_env(self, server: FakeSSEServer | None) -> dict[str, str]:
        env = os.environ.copy()
        for name in _PROXY_VARIABLES:
            env.pop(name, None)
        env["NO_PROXY"] = "127.0.0.1,localhost"
        env["no_proxy"] = "127.0.0.1,localhost"
        env["PA_API_KEY"] = "verify-key"
        env["PA_MODEL"] = "deepseek-flash"
        env["PA_MAX_STEPS"] = "5"
        env["PA_BASE_URL"] = server.base_url if server is not None else _UNREACHABLE_BASE_URL
        source_root = str(Path(__file__).resolve().parents[2])
        pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = f"{source_root}{os.pathsep}{pythonpath}" if pythonpath else source_root
        return env

    def check_api_request(self) -> None:
        with self.workspace() as cwd:
            with self.fake_server([_text_script("Hello API")]) as server:
                result = self.run_cli(["-p", "hello"], cwd=cwd, server=server)
                requests = list(server.requests)
        self.expect_equal("exit code", result.returncode, 0)
        self.expect_equal("request count", len(requests), 1)
        request = requests[0] if requests else {}
        tools = request.get("tools") or []
        messages = request.get("messages") or []
        tool_names = [
            (tool.get("function") or {}).get("name", "") for tool in tools if isinstance(tool, dict)
        ]
        stream_options = request.get("stream_options") or {}
        self.note(
            "request",
            f"model={request.get('model')} stream={str(request.get('stream')).lower()} "
            f"include_usage={str(stream_options.get('include_usage')).lower()} "
            f"tools={','.join(tool_names)}",
        )
        self.expect_equal("model", request.get("model"), "deepseek-flash")
        self.expect_equal("stream", request.get("stream"), True)
        self.expect_equal("stream_options", request.get("stream_options"), {"include_usage": True})
        self.expect_equal("tool names", tool_names, ["bash", "read", "write", "edit"])
        self.expect_equal(
            "first message role", messages[0].get("role") if messages else None, "system"
        )
        self.expect_equal(
            "last user message",
            messages[-1] if messages else None,
            {"role": "user", "content": "hello"},
        )
        self.expect_in("Hello API", result.output, "stdout")

    def check_cli_terminal(self) -> None:
        with self.workspace() as cwd:
            version = self.run_cli(["--version"], cwd=cwd)
            help_result = self.run_cli(["--help"], cwd=cwd)
        self.note("version", version.output.strip())
        self.note("help", help_result.output.strip().splitlines()[0] if help_result.output else "")
        self.expect_equal("version exit code", version.returncode, 0)
        self.expect_in("pa 0.1.0", version.output, "version stdout")
        self.expect_equal("help exit code", help_result.returncode, 0)
        self.expect_in("usage: pa", help_result.output, "help stdout")

    def check_repl(self) -> None:
        with self.workspace() as cwd:
            with self.fake_server([_text_script("Hello REPL")]) as server:
                with self.launch_cli([], cwd=cwd, server=server, terminal=True) as process:
                    banner = process.read_until("Type /help for commands.", self._timeout)
                    process.send("/help\n")
                    help_text = process.read_until("Commands:", self._timeout)
                    process.send("hello\n")
                    reply = process.read_until("Hello REPL", self._timeout)
                    tokens = process.read_until("[tokens]", self._timeout)
                    process.send("/new\n")
                    new_text = process.read_until("New conversation.", self._timeout)
                    process.send("/exit\n")
                    tail = process.read_all(self._timeout)
                    returncode = process.wait(self._timeout)
        transcript = banner + help_text + reply + tokens + new_text + tail
        self.note("transcript", f"{len(transcript)} bytes, exit {returncode}")
        self.expect_in("pa 0.1.0", banner, "banner")
        self.expect_in("deepseek-flash", banner, "banner model")
        self.expect_in(str(cwd), banner, "banner cwd")
        self.expect_in("Commands:", help_text, "/help output")
        self.expect_in("Hello REPL", reply, "reply")
        self.expect_in("[tokens]", tokens, "usage line")
        self.expect_in("New conversation.", new_text, "/new output")
        self.expect_equal("exit code", returncode, 0)

    def check_sse_streaming(self) -> None:
        started = time.monotonic()
        with self.workspace() as cwd:
            with self.fake_server([_streaming_script()]) as server:
                with self.launch_cli(["-p", "stream"], cwd=cwd, server=server) as process:
                    first = process.read_until("Hello", self._timeout)
                    first_delta = time.monotonic() - started
                    self.expect(process.running, "CLI exited before the stream finished")
                    rest = process.read_all(self._timeout)
                    stream_end = time.monotonic() - started
                    returncode = process.wait(self._timeout)
        gap = stream_end - first_delta
        self.note("first_delta_seconds", f"{first_delta:.2f}")
        self.note("gap_seconds", f"{gap:.2f}")
        self.expect_in("Hello", first, "first text delta")
        self.expect_in(" world", rest, "delayed text delta")
        self.expect_equal("exit code", returncode, 0)
        self.expect(
            gap >= 1.0,
            f"first text arrived {gap:.2f}s before stream end; expected >= 1.0s",
        )

    def check_reasoning(self) -> None:
        with self.workspace() as cwd:
            with self.fake_server([_reasoning_script()]) as server:
                result = self.run_cli(["-p", "think"], cwd=cwd, server=server)
                requests = list(server.requests)
        self.expect_equal("exit code", result.returncode, 0)
        self.expect_equal("request count", len(requests), 1)
        request = requests[0] if requests else {}
        self.note("reasoning_effort", str(request.get("reasoning_effort")))
        self.note("thinking", json.dumps(request.get("thinking")))
        self.expect_equal("reasoning_effort", request.get("reasoning_effort"), "high")
        self.expect_equal("thinking", request.get("thinking"), {"type": "enabled"})
        self.expect_in("Think.", result.output, "stdout reasoning")
        self.expect_in("Answer.", result.output, "stdout answer")

    def check_tool_roundtrip(self) -> None:
        command = "printf 'verify-tool-ok\\n' | tee artifact.txt"
        with self.workspace() as cwd:
            with self.fake_server(_tool_scripts(command)) as server:
                result = self.run_cli(["-p", "say hello"], cwd=cwd, server=server)
                requests = list(server.requests)
                artifact_path = cwd / "artifact.txt"
                artifact = artifact_path.read_text() if artifact_path.is_file() else ""
        self.expect_equal("exit code", result.returncode, 0)
        self.expect_equal("request count", len(requests), 2)
        self.note("requests", str(len(requests)))
        self.note("tool_call_id", "call_1")
        self.note("artifact", artifact.strip())
        self.expect_in("verify-tool-ok", artifact, "artifact.txt")
        self.expect_in("Done.", result.output, "stdout")
        messages = list(requests[1].get("messages") or []) if len(requests) > 1 else []
        call_index: int | None = None
        call: dict[str, object] | None = None
        for index, message in enumerate(messages):
            if message.get("role") != "assistant":
                continue
            for candidate in message.get("tool_calls") or []:
                if candidate.get("id") == "call_1":
                    call_index = index
                    call = candidate
                    break
            if call is not None:
                break
        self.expect(call is not None, "request 2: missing assistant tool call 'call_1'")
        self.expect_equal(
            "tool call function", ((call or {}).get("function") or {}).get("name"), "bash"
        )
        following = (
            messages[call_index + 1]
            if call_index is not None and call_index + 1 < len(messages)
            else {}
        )
        self.expect_equal("tool message role", following.get("role"), "tool")
        self.expect_equal("tool message call id", following.get("tool_call_id"), "call_1")
        self.expect_in("verify-tool-ok", following.get("content") or "", "tool message")

    def check_read_tool(self) -> None:
        with self.workspace() as cwd:
            (cwd / "notes.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
            with self.fake_server(
                _tool_call_scripts("read", {"path": "notes.txt", "start": 2, "end": 3})
            ) as server:
                result = self.run_cli(["-p", "read the notes"], cwd=cwd, server=server)
                requests = list(server.requests)
        self.expect_equal("exit code", result.returncode, 0)
        self.expect_equal("request count", len(requests), 2)
        messages = _request_messages(requests, 1)
        call, following = _tool_exchange(messages, "call_1")
        self.expect(call is not None, "request 2: missing assistant tool call 'call_1'")
        function = (call or {}).get("function") or {}
        self.expect_equal("tool call function", function.get("name"), "read")
        content = following.get("content") or ""
        self.note("tool", "read notes.txt 2-3")
        self.note("observation", content.splitlines()[0] if content else "")
        self.expect_in("lines 2-3 of 3", content, "tool message")
        self.expect_in("     2\tbeta", content, "tool message numbered line")
        self.expect_in("[read: lines 2-3 of 3]", result.output, "stdout")

    def check_write_tool(self) -> None:
        with self.workspace() as cwd:
            with self.fake_server(
                _tool_call_scripts(
                    "write", {"path": "created.txt", "content": "created by verify\n"}
                )
            ) as server:
                result = self.run_cli(["-p", "create a file"], cwd=cwd, server=server)
                requests = list(server.requests)
                created_path = cwd / "created.txt"
                created = created_path.read_text(encoding="utf-8") if created_path.is_file() else ""
        self.expect_equal("exit code", result.returncode, 0)
        self.expect_equal("request count", len(requests), 2)
        messages = _request_messages(requests, 1)
        call, following = _tool_exchange(messages, "call_1")
        self.expect(call is not None, "request 2: missing assistant tool call 'call_1'")
        function = (call or {}).get("function") or {}
        self.expect_equal("tool call function", function.get("name"), "write")
        self.expect_equal("written content", created, "created by verify\n")
        self.note("tool", "write created.txt")
        self.note("bytes", str(len(created.encode("utf-8"))))
        self.expect_in("Wrote 18 bytes", following.get("content") or "", "tool message")
        self.expect_in("[write: Wrote 18 bytes to created.txt]", result.output, "stdout")

        with self.workspace() as cwd:
            (cwd / "notes.txt").write_text("alpha\n", encoding="utf-8")
            with self.fake_server(
                _tool_call_scripts("write", {"path": "notes.txt", "content": "replacement"})
            ) as server:
                refusal = self.run_cli(["-p", "overwrite the file"], cwd=cwd, server=server)
                unchanged = (cwd / "notes.txt").read_text(encoding="utf-8")
        self.expect_equal("existing write exit code", refusal.returncode, 0)
        self.expect_in("already exists; use edit", refusal.output, "existing write stdout")
        self.expect_equal("existing file unchanged", unchanged, "alpha\n")

    def check_edit_tool(self) -> None:
        with self.workspace() as cwd:
            (cwd / "notes.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
            with self.fake_server(
                _tool_call_scripts(
                    "edit",
                    {"path": "notes.txt", "start": 2, "end": 2, "content": "BETA\n"},
                )
            ) as server:
                result = self.run_cli(["-p", "edit the notes"], cwd=cwd, server=server)
                requests = list(server.requests)
                edited = (cwd / "notes.txt").read_text(encoding="utf-8")
        self.expect_equal("exit code", result.returncode, 0)
        self.expect_equal("request count", len(requests), 2)
        messages = _request_messages(requests, 1)
        call, following = _tool_exchange(messages, "call_1")
        self.expect(call is not None, "request 2: missing assistant tool call 'call_1'")
        function = (call or {}).get("function") or {}
        self.expect_equal("tool call function", function.get("name"), "edit")
        self.expect_equal("edited content", edited, "alpha\nBETA\ngamma\n")
        self.note("tool", "edit notes.txt 2-2")
        self.note("edited", edited.strip())
        self.expect_in(
            "Edited notes.txt: replaced lines 2-2 of 3",
            following.get("content") or "",
            "tool message",
        )
        self.expect_in("[edit: Edited notes.txt: replaced lines 2-2 of 3]", result.output, "stdout")

        with self.workspace() as cwd:
            with self.fake_server(
                _tool_call_scripts(
                    "edit",
                    {"path": "missing.txt", "start": 1, "end": 1, "content": "x"},
                )
            ) as server:
                missing = self.run_cli(["-p", "edit a missing file"], cwd=cwd, server=server)
        self.expect_equal("missing edit exit code", missing.returncode, 0)
        self.expect_in("does not exist; use write", missing.output, "missing edit stdout")

    def check_workspace_boundary(self) -> None:
        with self.workspace() as cwd:
            (cwd / "notes.txt").write_text("alpha\n", encoding="utf-8")
            with self.fake_server(
                _tool_call_scripts("read", {"path": "../escaped-read.txt"})
            ) as server:
                read_result = self.run_cli(["-p", "read outside"], cwd=cwd, server=server)
                read_requests = list(server.requests)
            with self.fake_server(
                _tool_call_scripts("write", {"path": "../escaped-write.txt", "content": "nope"})
            ) as server:
                write_result = self.run_cli(["-p", "write outside"], cwd=cwd, server=server)
                write_requests = list(server.requests)
            read_target = cwd.parent / "escaped-read.txt"
            write_target = cwd.parent / "escaped-write.txt"
            escaped_read_exists = read_target.exists()
            escaped_write_exists = write_target.exists()
        self.expect_equal("read exit code", read_result.returncode, 0)
        self.expect_equal("write exit code", write_result.returncode, 0)
        read_call, read_following = _tool_exchange(_request_messages(read_requests, 1), "call_1")
        write_call, write_following = _tool_exchange(_request_messages(write_requests, 1), "call_1")
        self.expect(read_call is not None, "request 2: missing read tool call")
        self.expect(write_call is not None, "request 2: missing write tool call")
        self.note("read escape", "rejected")
        self.note("write escape", "rejected")
        self.expect_in(
            "resolves outside the workspace",
            read_following.get("content") or "",
            "read tool message",
        )
        self.expect_in(
            "resolves outside the workspace",
            write_following.get("content") or "",
            "write tool message",
        )
        self.expect(not escaped_read_exists, "read escape created an outside file")
        self.expect(not escaped_write_exists, "write escape created an outside file")


CHECKS: tuple[Check, ...] = (
    Check("api-request", 1, "Correct API request", VerificationSession.check_api_request),
    Check("cli-terminal", 2, "CLI runs in a terminal", VerificationSession.check_cli_terminal),
    Check("repl", 3, "Interactive REPL", VerificationSession.check_repl),
    Check(
        "sse-streaming",
        4,
        "SSE streams before the stream ends",
        VerificationSession.check_sse_streaming,
    ),
    Check("reasoning", 5, "Reasoning enabled in the request", VerificationSession.check_reasoning),
    Check(
        "tool-roundtrip",
        6,
        "Bash tool round-trips into the next request",
        VerificationSession.check_tool_roundtrip,
    ),
    Check("read-tool", 7, "Read tool returns numbered lines", VerificationSession.check_read_tool),
    Check(
        "write-tool", 8, "Write tool creates new files only", VerificationSession.check_write_tool
    ),
    Check("edit-tool", 9, "Edit tool replaces a line range", VerificationSession.check_edit_tool),
    Check(
        "workspace-boundary",
        10,
        "File tools stay inside the workspace",
        VerificationSession.check_workspace_boundary,
    ),
)


def run_checks(checks: Sequence[Check], *, timeout: float = 30.0) -> Report:
    """Run selected checks sequentially, each with a fresh workspace and server."""
    started = time.monotonic()
    with VerificationSession(timeout=timeout) as session:
        results = session.run_all(checks)
    return Report(results=results, duration_ms=round((time.monotonic() - started) * 1000))


def _short(value: object) -> str:
    text = repr(value)
    return text if len(text) <= _OUTPUT_TAIL else f"{text[:_OUTPUT_TAIL]}..."


def _text_script(text: str) -> list[SSEEvent]:
    return [
        (0.0, chunk(delta={"content": text})),
        (0.0, chunk(delta={}, finish_reason="stop")),
        (0.0, chunk(usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})),
        (0.0, DONE),
    ]


def _reasoning_script() -> list[SSEEvent]:
    return [
        (0.0, chunk(delta={"reasoning_content": "Think."})),
        (0.0, chunk(delta={"content": "Answer."})),
        (0.0, chunk(delta={}, finish_reason="stop")),
        (0.0, chunk(usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})),
        (0.0, DONE),
    ]


def _streaming_script() -> list[SSEEvent]:
    return [
        (0.0, chunk(delta={"content": "Hello"})),
        (2.0, chunk(delta={"content": " world"})),
        (0.0, chunk(delta={}, finish_reason="stop")),
        (0.0, chunk(usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})),
        (0.0, DONE),
    ]


def _tool_scripts(command: str) -> list[list[SSEEvent]]:
    return _tool_call_scripts("bash", {"command": command})


def _tool_call_scripts(name: str, arguments: dict[str, object]) -> list[list[SSEEvent]]:
    raw_arguments = json.dumps(arguments)
    first: list[SSEEvent] = [
        (
            0.0,
            chunk(
                delta={
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": name, "arguments": raw_arguments},
                        }
                    ]
                }
            ),
        ),
        (0.0, chunk(delta={}, finish_reason="tool_calls")),
        (0.0, chunk(usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15})),
        (0.0, DONE),
    ]
    return [first, _text_script("Done.")]


def _request_messages(requests: Sequence[dict[str, Any]], index: int) -> list[dict[str, Any]]:
    if len(requests) <= index:
        return []
    return list(requests[index].get("messages") or [])


def _tool_exchange(
    messages: Sequence[dict[str, Any]], call_id: str
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    for index, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        for candidate in message.get("tool_calls") or []:
            if isinstance(candidate, dict) and candidate.get("id") == call_id:
                following = messages[index + 1] if index + 1 < len(messages) else {}
                return candidate, following
    return None, {}
