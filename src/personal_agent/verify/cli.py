"""The `pa-verify` command: argparse and report rendering."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence

from personal_agent import __version__

from .checks import CHECKS, Check, Report, run_checks


class UsageError(Exception):
    """A caller supplied an unknown check id or an empty selection."""


def _positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid timeout: {value!r}") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive number")
    return seconds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pa-verify",
        description="Verify the ten acceptance criteria offline against the real `pa` CLI.",
    )
    parser.add_argument("--list", action="store_true", help="list checks and exit")
    parser.add_argument(
        "--only",
        action="append",
        metavar="ID[,ID]",
        help="run only the named checks; repeatable",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    parser.add_argument(
        "--timeout",
        type=_positive_seconds,
        default=30.0,
        metavar="SECONDS",
        help="per-process timeout in seconds (default: 30)",
    )
    parser.add_argument("--version", action="version", version=f"pa-verify {__version__}")
    return parser


def select_checks(only: Sequence[str] | None) -> tuple[Check, ...]:
    """Return the selected checks in registry order, or raise UsageError."""
    if not only:
        return CHECKS
    names = [part.strip() for value in only for part in value.split(",")]
    if not names or any(not name for name in names):
        raise UsageError("empty check id in --only")
    known = {check.id for check in CHECKS}
    unknown = [name for name in names if name not in known]
    if unknown:
        available = ", ".join(check.id for check in CHECKS)
        raise UsageError(f"unknown check id: {', '.join(unknown)}; available: {available}")
    wanted = set(names)
    return tuple(check for check in CHECKS if check.id in wanted)


def format_list(checks: Sequence[Check]) -> str:
    return "\n".join(f"{check.id} | AC-{check.criterion} | {check.title}" for check in checks)


def format_list_json(checks: Sequence[Check]) -> str:
    payload = {
        "version": __version__,
        "checks": [
            {"id": check.id, "criterion": check.criterion, "title": check.title} for check in checks
        ],
    }
    return json.dumps(payload, indent=2)


def format_human(report: Report) -> str:
    count = len(report.results)
    noun = "check" if count == 1 else "checks"
    lines = [f"pa-verify {__version__} | {count} {noun}", ""]
    for result in report.results:
        lines.append(
            f"{result.status.upper()} {result.check.id} (AC-{result.check.criterion}) "
            f"{result.duration_ms / 1000:.2f}s {result.check.title}"
        )
        lines.extend(f"     {item.label}: {item.value}" for item in result.evidence)
        if result.failure is not None:
            lines.append(f"     failure: {result.failure}")
    passed = sum(result.status == "pass" for result in report.results)
    failed = count - passed
    lines.extend(["", f"{passed} passed, {failed} failed in {report.duration_ms / 1000:.2f}s"])
    return "\n".join(lines)


def format_json(report: Report) -> str:
    payload = {
        "schema": 1,
        "ok": report.ok,
        "duration_ms": report.duration_ms,
        "checks": [
            {
                "id": result.check.id,
                "criterion": result.check.criterion,
                "title": result.check.title,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "evidence": [
                    {"label": item.label, "value": item.value} for item in result.evidence
                ],
                "failure": result.failure,
            }
            for result in report.results
        ],
    }
    return json.dumps(payload, indent=2)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        selected = select_checks(args.only)
    except UsageError as exc:
        print(f"pa-verify: {exc}", file=sys.stderr)
        return 2
    if args.list:
        print(format_list_json(selected) if args.json else format_list(selected))
        return 0
    report = run_checks(selected, timeout=args.timeout)
    print(format_json(report) if args.json else format_human(report))
    return 0 if report.ok else 1
