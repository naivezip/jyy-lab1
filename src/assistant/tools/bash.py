"""bash: run a shell command in the working directory."""

from __future__ import annotations

import subprocess

from assistant.tools.base import Tool, ToolSpec, truncate


def build(cwd: str) -> Tool:
    def handler(command: str, timeout: int = 120) -> str:
        try:
            completed = subprocess.run(
                ["bash", "-lc", command],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=max(1, int(timeout)),
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Command timed out after {timeout}s: {command}")

        parts = [f"exit code: {completed.returncode}"]
        if completed.stdout:
            parts.append(f"--- stdout ---\n{completed.stdout.rstrip()}")
        if completed.stderr:
            parts.append(f"--- stderr ---\n{completed.stderr.rstrip()}")
        return truncate("\n".join(parts))

    return Tool(
        spec=ToolSpec(
            name="bash",
            description="Run a bash command. Returns exit code, stdout and stderr.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run with bash -lc"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 120},
                },
                "required": ["command"],
            },
        ),
        handler=handler,
    )
