"""Bash tool: run a shell command in the workspace."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

MAX_TOOL_OUTPUT = 16_000
DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600

BASH_TOOL_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Run a bash command in the working directory. Returns the exit code, stdout and stderr."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to run with bash -lc",
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        f"Timeout in seconds (default {DEFAULT_TIMEOUT}, max {MAX_TIMEOUT})"
                    ),
                },
            },
            "required": ["command"],
        },
    },
}


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n\n[truncated: {omitted} more characters omitted]"


@dataclass(frozen=True)
class BashTool:
    cwd: str

    def run(self, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Execute a bash command and return (observation, is_error). Never raises."""
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            return ("bash: 'command' must be a non-empty string", True)

        try:
            timeout = int(arguments.get("timeout", DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            return ("bash: 'timeout' must be an integer", True)
        timeout = max(1, min(timeout, MAX_TIMEOUT))

        try:
            completed = subprocess.run(
                ["bash", "-lc", command],
                cwd=self.cwd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return (f"Command timed out after {timeout}s: {command}", True)
        except OSError as exc:
            return (f"Could not run command: {exc}", True)

        parts = [f"exit code: {completed.returncode}"]
        if completed.stdout:
            parts.append(f"--- stdout ---\n{completed.stdout.rstrip()}")
        if completed.stderr:
            parts.append(f"--- stderr ---\n{completed.stderr.rstrip()}")
        return (truncate("\n".join(parts)), completed.returncode != 0)
