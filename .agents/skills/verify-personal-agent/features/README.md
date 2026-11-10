# personal-agent verification map

This directory is the maintained source for verifying the user-facing behavior of personal-agent. Read the index before driving the app, then use the matching feature file as the recipe.

## Baseline preconditions

- Run `uv sync` once from the repository root.
- Run `uv run pa-verify --json` and require exit code 0, `"ok": true`, and six `"status": "pass"` checks before driving a feature.
- Set a unique `RUN_ID` and keep proof under `artifacts/verify-personal-agent/$RUN_ID/<feature>/`.
- Use `pa_harness.py` for feature journeys. It starts a local fake OpenAI-compatible SSE server, injects `PA_API_KEY=verify-key`, and runs the real `pa` CLI in a temporary workspace.
- Do not use a real API key or the public DeepSeek endpoint for verification. Do not drive an instance that this run did not start.

## Driving conventions

- Run every command from the repository root.
- Invoke the helper as `uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py`.
- Treat every command as literal. Keep quoted prompts and flags unchanged.
- Use `pa-verify --only <id> --json` for acceptance-level checks and `pa_harness.py` for user journeys with custom prompts.
- Capture the action and the resulting state. A final screen without the command, exit code, or side effect is not enough.

## Proof and skip reporting

- CLI proof includes the command, combined stdout and stderr, and exit code.
- Mutation proof includes a second read of the written file, not only the rendered message.
- Tool proof includes `artifact.txt` and the second request in `requests.json`.
- File-tool proof includes `files.json` and `artifact.txt`; a read proof shows the `lines a-b of N` header and six-width numbered lines.
- Workspace proof includes the rejected path in `output.txt` and `files.json` showing no outside file was read or created.
- Streaming proof includes `timings.json` and checks that the first text arrived before the stream ended.
- Record the feature ID and entry point used with every artifact.
- Report an unreachable path with the attempted command and the unmet precondition. Do not report a skipped entry point as verified through a different path.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with pa_harness.py` starts with `Preconditions:` and pairs each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands, and observable proof.

## Features

- [One-shot prompts](./one-shot.md) covers `pa -p`, answer output, token usage, and model override.
- [Interactive REPL](./repl.md) covers startup, chat, `/help`, `/new`, and `/exit` through a PTY.
- [Streaming and reasoning](./streaming-reasoning.md) covers incremental text, reasoning display, and the reasoning request fields.
- [Bash tool](./bash-tool.md) covers tool execution, the observation returned to the model, and a file side effect.
- [Read tool](./read-tool.md) covers numbered file reads, line-range paging, and the `lines a-b of N` header.
- [Write tool](./write-tool.md) covers creating files, parent directories, and refusing to modify an existing file.
- [Edit tool](./edit-tool.md) covers replacing a 1-based inclusive line range and directing missing files to `write`.
- [Workspace boundary](./workspace.md) covers relative paths, absolute paths inside the root, and rejected escapes.
- [CLI basics](./cli-basics.md) covers `--version`, `--help`, and missing-key exits.
