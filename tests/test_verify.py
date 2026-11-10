"""Black-box tests for the `pa-verify` command."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY_IDS = [
    "api-request",
    "cli-terminal",
    "repl",
    "sse-streaming",
    "reasoning",
    "tool-roundtrip",
    "read-tool",
    "write-tool",
    "edit-tool",
    "workspace-boundary",
]
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def verify_environment() -> dict[str, str]:
    env = os.environ.copy()
    for name in PROXY_VARIABLES:
        env.pop(name, None)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    env["PYTHONPATH"] = str(ROOT / "src")
    env.pop("PA_API_KEY", None)
    return env


def run_verify(*args: str, timeout: float = 180.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "personal_agent.verify", *args],
        cwd=ROOT,
        env=verify_environment(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_list_prints_registry_order() -> None:
    result = run_verify("--list")

    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert [line.split(" | ")[0] for line in lines] == VERIFY_IDS
    assert all(" | AC-" in line for line in lines)


def test_list_json_is_machine_readable() -> None:
    result = run_verify("--list", "--json")

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["version"] == "0.1.0"
    assert [check["id"] for check in data["checks"]] == VERIFY_IDS


def test_full_run_json_reports_ten_passes() -> None:
    result = run_verify("--json")

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["schema"] == 1
    assert data["ok"] is True
    assert [check["id"] for check in data["checks"]] == VERIFY_IDS
    assert all(check["status"] == "pass" for check in data["checks"])
    assert all(check["evidence"] for check in data["checks"])


def test_only_selects_one_check() -> None:
    result = run_verify("--only", "repl", "--json")

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert [check["id"] for check in data["checks"]] == ["repl"]


def test_only_accepts_comma_and_repeated_values_in_registry_order() -> None:
    result = run_verify(
        "--only",
        "tool-roundtrip,api-request",
        "--only",
        "reasoning",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert [check["id"] for check in data["checks"]] == [
        "api-request",
        "reasoning",
        "tool-roundtrip",
    ]


def test_short_timeout_fails_one_check() -> None:
    result = run_verify("--only", "cli-terminal", "--timeout", "0.001", "--json")

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert len(data["checks"]) == 1
    assert data["checks"][0]["status"] == "fail"
    assert data["checks"][0]["failure"]


def test_short_timeout_still_reports_all_ten() -> None:
    result = run_verify("--timeout", "0.001", "--json")

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert [check["id"] for check in data["checks"]] == VERIFY_IDS
    assert all(check["status"] == "fail" for check in data["checks"])


def test_unknown_check_is_usage_error() -> None:
    result = run_verify("--only", "nope")

    assert result.returncode == 2
    assert "unknown check" in result.stderr
    assert result.stdout == ""


def test_empty_check_id_is_usage_error() -> None:
    result = run_verify("--only", "")

    assert result.returncode == 2
    assert "empty check id" in result.stderr


def test_help_and_version() -> None:
    help_result = run_verify("--help")
    version_result = run_verify("--version")

    assert help_result.returncode == 0
    assert "usage: pa-verify" in help_result.stdout
    assert version_result.returncode == 0
    assert version_result.stdout.strip() == "pa-verify 0.1.0"


def test_json_stdout_is_pure() -> None:
    result = run_verify("--only", "cli-terminal", "--json")

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("{")
    json.loads(result.stdout)
