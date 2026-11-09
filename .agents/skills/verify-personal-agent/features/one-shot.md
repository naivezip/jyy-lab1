# One-shot prompts

One-shot mode lets a user send one prompt from the terminal, stream the answer, see the token usage, and exit without starting a REPL.

## Sub-features

- `one-shot-answer` sends one prompt and prints the model reply.
- `one-shot-usage` prints one `[tokens] input=... output=...` line after the reply.
- `one-shot-model` accepts `--model` for a single run and lets it win over `PA_MODEL`.

## How to get to it (user POV)

- Run `uv run pa -p "explain this repo"` from the repository root.
- Run `uv run pa --model deepseek -p "say hello"` to override the model for that run.
- Run `uv run pa -p ""` when an empty one-shot prompt is needed. It still starts a turn.

## Driving it with pa_harness.py

Preconditions:

- `uv sync` has completed and `uv run pa-verify --json` reports six passes.
- The helper can reach the repository root and imports the installed `personal_agent` package.
- The output directory does not exist yet or is empty.

- **Send one prompt.** Run `uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py one-shot --prompt "Say hello" --reply "Hello from the verification model." --out artifacts/verify-personal-agent/<run-id>/one-shot`. `exit_code.txt` reads `0`, `output.txt` contains `Hello from the verification model.` and one `[tokens] input=10 output=2` line, and `requests.json` contains exactly one request whose last message is `{"role": "user", "content": "Say hello"}`.
- **Override the model.** Run the same command with `--model deepseek` and `--out artifacts/verify-personal-agent/<run-id>/one-shot-model`. `requests.json` shows `"model": "deepseek"` for the request and `output.txt` contains the fake reply.
- **Record proof.** Keep `argv.txt`, `meta.json`, `output.txt`, `exit_code.txt`, and `requests.json` under the output directory. Reopen `output.txt` after the helper exits to confirm the answer survives cleanup.

## Gotchas

- `pa -p ""` is still one-shot mode because the CLI checks `prompt is not None`, not truthiness.
- Direct `pa` calls need a real `PA_API_KEY` and a reachable model endpoint. The helper injects a fake key and local server and must not be replaced by a real call for verification.
- `pa` loads `.env` from its current working directory. The helper runs in a temporary workspace, so a developer `.env` cannot leak into the request.
- The token counts in the fake script are fixed at `input=10 output=2`. A real model returns different numbers.
