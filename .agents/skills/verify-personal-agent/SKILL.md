---
name: verify-personal-agent
description: "Verify the personal-agent `pa` terminal CLI. Use before claiming the agent works or after changing its CLI, streaming, reasoning, configuration, bash tool, or file tools; drives the real binary offline through pa-verify and a local fake model."
---

# Verify personal-agent

The primary surface is the `pa` terminal CLI. A user runs one prompt with `pa -p`, or starts an interactive REPL with `pa`. `pa-verify` is the project's offline acceptance command and the harness this skill uses for deterministic journeys.

## Launch

Run these from the repository root once per checkout:

```bash
uv sync
uv run pa --version
```

`uv run pa --version` prints `pa 0.1.0`. A real interactive launch is `uv run pa`, which prints a ready banner and prompt:

```text
pa 0.1.0 | deepseek-flash | /path/to/workspace
Type /help for commands.

>
```

A real launch reads `PA_API_KEY`, `PA_MODEL`, `PA_BASE_URL`, and `PA_MAX_STEPS` from the environment, then from `.env` in the current working directory. Verification does not need a real key. `pa-verify` and `pa_harness.py` start a local fake OpenAI-compatible SSE server, inject `PA_API_KEY=verify-key`, and use a fresh temporary workspace.

There is no server to keep alive. Each drive is a short-lived `pa` process. A REPL drive ends with `/exit` or Ctrl-D.

## Doctor

Run the read-only acceptance check before driving any feature:

```bash
uv run pa-verify --json
```

Require exit code 0, `"ok": true`, six checks, and `"status": "pass"` for every check. If it fails, stop. Report the check id and its `failure` from the JSON, and do not claim a feature was verified. `uv run pa-verify --list` prints the check ids. `uv run pa --version` must also print `pa 0.1.0`.

## Drive

Use the helper for feature journeys. It runs the real `pa` CLI with a scripted fake model and writes evidence. Replace `<run-id>` with one unique label for the verification run, for example `20261109-171500`:

```bash
uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py --help
uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py one-shot --prompt "Say hello" --reply "Hello from the verification model." --out artifacts/verify-personal-agent/<run-id>/one-shot
uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py repl --prompt hello --reply "Hello from the verification model." --out artifacts/verify-personal-agent/<run-id>/repl
uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py tool --out artifacts/verify-personal-agent/<run-id>/tool
uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py read --out artifacts/verify-personal-agent/<run-id>/read-tool
uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py write --out artifacts/verify-personal-agent/<run-id>/write-tool
uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py edit --out artifacts/verify-personal-agent/<run-id>/edit-tool
uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py streaming --reasoning "Think." --out artifacts/verify-personal-agent/<run-id>/streaming
```

`pa-verify` is the harness for acceptance-level checks and for the doctor:

```bash
uv run pa-verify --only api-request --json
uv run pa-verify --only repl --json
uv run pa-verify --only sse-streaming,reasoning --json
uv run pa-verify --only tool-roundtrip --json
uv run pa-verify --only cli-terminal --json
```

Read the matching file under `features/` before driving a feature. Every feature file names the exact command and observable state.

## Evidence

Keep every proof under `artifacts/verify-personal-agent/<run-id>/<feature>/`. The helper writes these files there:

- `argv.txt` records the exact helper invocation.
- `meta.json` records the working directory, repository root, Python path, and timestamp.
- `output.txt` or `transcript.txt` records what the user saw.
- `exit_code.txt` records the `pa` process status.
- `requests.json` records the OpenAI-compatible requests received by the fake server.
- `artifact.txt` records a file side effect when a tool wrote one.
- `files.json` records every workspace file after a read, write, or edit journey.
- `timings.json` records first-delta and stream-end timing for streaming checks.

For `pa-verify`, save the report and exit status:

```bash
uv run pa-verify --json > artifacts/verify-personal-agent/<run-id>/doctor.json
printf 'exit=%s\n' "$?" > artifacts/verify-personal-agent/<run-id>/doctor.exit
```

Proof standards:

- Exercise the real user path, not an internal setter or a test-only endpoint.
- Capture the action and the resulting state. A final screen alone is not enough.
- Verify side effects such as the artifact file and the second model request, not only visible text.
- File-tool proof includes the tool line, the `[read: lines …]`, `[write: Wrote …]`, or
  `[edit: Edited …]` observation, and the file in `files.json` plus `artifact.txt`. A read
  proof must show the `lines a-b of N` header and six-width numbered lines.
- Workspace-boundary proof passes a path such as `../outside.txt`; the observation must reject
  it and `files.json` must show that no outside file was created or read.
- Use the fake model only because the provider boundary is already isolated in `pa-verify` and `pa_harness.py`. Do not use a real API key for verification.
- Report an unavailable path with the attempted command and the unmet precondition. Do not mark it verified through a different path.

## Cleanup

`pa_harness.py` creates its fake server, workspace, and child processes through `VerificationSession`, then stops and removes them when the command exits. It leaves the `--out` directory in place. Do not delete evidence.

If a direct `pa` REPL is still running, send `/exit` or Ctrl-D. Never kill by process name. Kill only a PID that this run started. Remove scratch directories, never proof artifacts.

## Helpers

`scripts/pa_harness.py` is executable. Invoke it through `uv run python` from the repository root so it uses the project virtual environment. Subcommands are `one-shot`, `repl`, `tool`, `read`, `write`, `edit`, and `streaming`. Each accepts `--out` and `--timeout`; the file-tool subcommands also accept `--path`, `--seed PATH=TEXT`, and `--capture`. `--help` on the script or a subcommand shows the full interface.
