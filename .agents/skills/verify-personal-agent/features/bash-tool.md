# Bash tool

The bash tool lets the model run a shell command in the user's working directory, observe the exit code, stdout and stderr, and continue the turn with that observation.

## Sub-features

- `tool-call` requests a `bash` call with a command and becomes visible as `$ <command>`.
- `tool-run` executes the command with `bash -lc` in the workspace.
- `tool-observation` returns exit code, stdout and stderr to the model in a tool message.
- `tool-artifact` proves a side effect in the workspace.
- `tool-error` returns a failed command as an observation instead of crashing the agent.

## How to get to it (user POV)

- Ask the agent to inspect files or run a command, for example `uv run pa -p "create artifact.txt with a verification marker"`.
- Watch the `$ <command>` line and the `[bash: ...]` summary in the terminal.
- The model decides when to call the tool. There is no separate user command for it.

## Driving it with pa_harness.py

Preconditions:

- `uv sync` has completed and `uv run pa-verify --json` reports six passes.
- `bash` is available on the host.
- The output directory is fresh.

- **Request the tool.** Run `uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py tool --prompt "Create the verification artifact." --reply "Done." --out artifacts/verify-personal-agent/<run-id>/tool`. The helper serves a first response with a `bash` call for `printf 'verify-tool-ok\n' | tee artifact.txt`, then a second text response. `output.txt` contains `$ printf 'verify-tool-ok\n' | tee artifact.txt` and `Done.`; `exit_code.txt` reads `0`.
- **Confirm the side effect.** `artifact.txt` contains `verify-tool-ok`. This is a second user-facing view of what the command wrote, not just the renderer summary.
- **Confirm the model saw the observation.** `requests.json` contains exactly two requests. The second request contains an assistant message with a `tool_calls` entry for `call_1` followed by a `role: "tool"` message with `tool_call_id: "call_1"` and content containing `verify-tool-ok`.
- **Check failure handling.** Run the helper with `--command "exit 7"` and a fresh output directory. `exit_code.txt` remains `0` for the overall turn, `output.txt` contains `[bash: exit code: 7]`, and `requests.json` shows the tool message content beginning with `exit code: 7`.

## Gotchas

- The command runs with `bash -lc` and `stdin=DEVNULL`. Interactive prompts and shell variables do not persist between calls.
- The workspace is a temporary directory owned by the helper. Relative paths in the command resolve there, not in the repository.
- Tool output is truncated at 16,000 characters. Do not use the tool to prove large outputs without checking the truncation marker.
- A tool command failure is an observation with `is_error=True`; the turn can still finish successfully. Assert the tool message content, not only the `$` line.
- The fake server reuses its last script if a third request appears. The `tool-roundtrip` acceptance check asserts exactly two requests, but a feature proof should still read `requests.json`.
