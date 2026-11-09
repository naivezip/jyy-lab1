#!/usr/bin/env python3
"""Drive the `pa` CLI against a local fake model and save verification evidence."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from personal_agent.verify.checks import VerificationSession
from personal_agent.verify.fake_server import DONE, chunk

ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file()
)


def text_script(
    text: str, reasoning: str | None = None
) -> list[tuple[float, dict[str, object] | str]]:
    script: list[tuple[float, dict[str, object] | str]] = []
    if reasoning:
        script.append((0.0, chunk(delta={"reasoning_content": reasoning})))
    script.extend(
        [
            (0.0, chunk(delta={"content": text})),
            (0.0, chunk(delta={}, finish_reason="stop")),
            (0.0, chunk(usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})),
            (0.0, DONE),
        ]
    )
    return script


def tool_scripts(command: str, reply: str) -> list[list[tuple[float, dict[str, object] | str]]]:
    arguments = json.dumps({"command": command})
    first: list[tuple[float, dict[str, object] | str]] = [
        (
            0.0,
            chunk(
                delta={
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "bash", "arguments": arguments},
                        }
                    ]
                }
            ),
        ),
        (0.0, chunk(delta={}, finish_reason="tool_calls")),
        (0.0, chunk(usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15})),
        (0.0, DONE),
    ]
    return [first, text_script(reply)]


def prepare(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "argv.txt").write_text(" ".join(sys.argv) + "\n", encoding="utf-8")
    (out / "meta.json").write_text(
        json.dumps(
            {
                "cwd": str(Path.cwd()),
                "root": str(ROOT),
                "python": sys.executable,
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_requests(out: Path, requests: list[dict[str, object]]) -> None:
    (out / "requests.json").write_text(json.dumps(requests, indent=2) + "\n", encoding="utf-8")


def run_one_shot(args: argparse.Namespace) -> int:
    with VerificationSession(timeout=args.timeout) as session:
        with session.workspace() as cwd:
            with session.fake_server([text_script(args.reply, args.reasoning)]) as server:
                command = ["-p", args.prompt]
                if args.model:
                    command.extend(["--model", args.model])
                result = session.run_cli(command, cwd=cwd, server=server)
                requests = list(server.requests)
    prepare(args.out)
    (args.out / "output.txt").write_text(result.output, encoding="utf-8")
    (args.out / "exit_code.txt").write_text(f"{result.returncode}\n", encoding="utf-8")
    write_requests(args.out, requests)
    return result.returncode


def run_repl(args: argparse.Namespace) -> int:
    with VerificationSession(timeout=args.timeout) as session:
        with session.workspace() as cwd:
            with session.fake_server([text_script(args.reply)]) as server:
                with session.launch_cli([], cwd=cwd, server=server, terminal=True) as process:
                    parts = [process.read_until("Type /help for commands.", args.timeout)]
                    process.send("/help\n")
                    parts.append(process.read_until("Commands:", args.timeout))
                    process.send(args.prompt + "\n")
                    parts.append(process.read_until(args.reply, args.timeout))
                    parts.append(process.read_until("[tokens]", args.timeout))
                    process.send("/new\n")
                    parts.append(process.read_until("New conversation.", args.timeout))
                    process.send("/exit\n")
                    parts.append(process.read_all(args.timeout))
                    returncode = process.wait(args.timeout)
                requests = list(server.requests)
    prepare(args.out)
    (args.out / "transcript.txt").write_text("".join(parts), encoding="utf-8")
    (args.out / "exit_code.txt").write_text(f"{returncode}\n", encoding="utf-8")
    write_requests(args.out, requests)
    return returncode


def run_tool(args: argparse.Namespace) -> int:
    with VerificationSession(timeout=args.timeout) as session:
        with session.workspace() as cwd:
            with session.fake_server(tool_scripts(args.command, args.reply)) as server:
                result = session.run_cli(["-p", args.prompt], cwd=cwd, server=server)
                requests = list(server.requests)
                artifact_path = cwd / "artifact.txt"
                artifact = (
                    artifact_path.read_text(encoding="utf-8") if artifact_path.is_file() else ""
                )
    prepare(args.out)
    (args.out / "output.txt").write_text(result.output, encoding="utf-8")
    (args.out / "artifact.txt").write_text(artifact, encoding="utf-8")
    (args.out / "exit_code.txt").write_text(f"{result.returncode}\n", encoding="utf-8")
    write_requests(args.out, requests)
    return result.returncode


def run_streaming(args: argparse.Namespace) -> int:
    script = []
    if args.reasoning:
        script.append((0.0, chunk(delta={"reasoning_content": args.reasoning})))
    script.extend(
        [
            (0.0, chunk(delta={"content": args.before})),
            (args.delay, chunk(delta={"content": args.after})),
            (0.0, chunk(delta={}, finish_reason="stop")),
            (0.0, chunk(usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})),
            (0.0, DONE),
        ]
    )
    with VerificationSession(timeout=args.timeout) as session:
        with session.workspace() as cwd:
            with session.fake_server([script]) as server:
                started = time.monotonic()
                with session.launch_cli(["-p", args.prompt], cwd=cwd, server=server) as process:
                    first = process.read_until(args.before, args.timeout)
                    first_delta = time.monotonic() - started
                    running = process.running
                    rest = process.read_all(args.timeout)
                    stream_end = time.monotonic() - started
                    returncode = process.wait(args.timeout)
                requests = list(server.requests)
    prepare(args.out)
    (args.out / "output.txt").write_text(first + rest, encoding="utf-8")
    (args.out / "timings.json").write_text(
        json.dumps(
            {
                "first_delta_seconds": round(first_delta, 3),
                "stream_end_seconds": round(stream_end, 3),
                "gap_seconds": round(stream_end - first_delta, 3),
                "running_after_first_delta": running,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (args.out / "exit_code.txt").write_text(f"{returncode}\n", encoding="utf-8")
    write_requests(args.out, requests)
    return returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pa_harness.py",
        description="Drive the pa CLI against a local fake model and save evidence.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    one_shot = subparsers.add_parser("one-shot", help="run pa -p against one fake reply")
    one_shot.add_argument("--prompt", default="Say hello in one short sentence.")
    one_shot.add_argument("--reply", default="Hello from the verification model.")
    one_shot.add_argument("--reasoning", default=None)
    one_shot.add_argument("--model", default=None)
    one_shot.add_argument("--out", type=Path, required=True)
    one_shot.add_argument("--timeout", type=float, default=30.0)
    one_shot.set_defaults(func=run_one_shot)

    repl = subparsers.add_parser("repl", help="drive the interactive REPL through a PTY")
    repl.add_argument("--prompt", default="hello")
    repl.add_argument("--reply", default="Hello from the verification model.")
    repl.add_argument("--out", type=Path, required=True)
    repl.add_argument("--timeout", type=float, default=30.0)
    repl.set_defaults(func=run_repl)

    tool = subparsers.add_parser("tool", help="drive one bash tool round trip")
    tool.add_argument("--prompt", default="Create the verification artifact.")
    tool.add_argument("--reply", default="Done.")
    tool.add_argument("--command", default="printf 'verify-tool-ok\\n' | tee artifact.txt")
    tool.add_argument("--out", type=Path, required=True)
    tool.add_argument("--timeout", type=float, default=30.0)
    tool.set_defaults(func=run_tool)

    streaming = subparsers.add_parser("streaming", help="measure streamed text timing")
    streaming.add_argument("--prompt", default="stream a sentence")
    streaming.add_argument("--before", default="Hello")
    streaming.add_argument("--after", default=" world")
    streaming.add_argument("--delay", type=float, default=1.5)
    streaming.add_argument("--reasoning", default=None)
    streaming.add_argument("--out", type=Path, required=True)
    streaming.add_argument("--timeout", type=float, default=30.0)
    streaming.set_defaults(func=run_streaming)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001 - surface a verification failure, not a traceback
        print(f"pa_harness: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
