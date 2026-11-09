# Streaming and reasoning

The agent streams answer text as the model produces it and streams `reasoning_content` separately before the answer. The request always enables reasoning.

## Sub-features

- `stream-first-delta` shows answer text before the model stream ends.
- `stream-complete` shows the delayed tail and the final token usage.
- `reasoning-request` sends `reasoning_effort="high"` and `thinking.type="enabled"`.
- `reasoning-display` prints reasoning text separately from the final answer.

## How to get to it (user POV)

- Run any one-shot prompt, for example `uv run pa -p "explain this repo"`, and watch the answer appear in pieces.
- Run `uv run pa` and send a prompt in the REPL. Reasoning is dimmed when stdout is a TTY.
- No flag turns reasoning on. It is always enabled in the request.

## Driving it with pa_harness.py

Preconditions:

- `uv sync` has completed and `uv run pa-verify --json` reports six passes.
- The helper can bind a local SSE server on `127.0.0.1:0`.
- The output directory is fresh.

- **Send a streamed prompt with reasoning.** Run `uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py streaming --prompt "stream a sentence" --before "Hello" --after " world" --delay 1.5 --reasoning "Think." --out artifacts/verify-personal-agent/<run-id>/streaming`. `timings.json` shows `first_delta_seconds` less than `stream_end_seconds`, a `gap_seconds` of at least `1.0`, and `running_after_first_delta` as `true`.
- **Read the visible output.** `output.txt` contains `Think.` and `Hello world`. The first text must be present before the delayed tail, not only at process exit.
- **Read the request contract.** `requests.json` contains one request with `"reasoning_effort": "high"` and `"thinking": {"type": "enabled"}`.
- **Read the usage line.** `output.txt` ends with `[tokens] input=10 output=2`; `exit_code.txt` reads `0`.

## Gotchas

- A 2.0 second server delay with a 1.0 second gap threshold proves streaming in the same process. A buffered renderer makes the first text and stream end arrive together, so the gap collapses.
- The fake server writes `Hello` immediately and ` world` after `delay` seconds. A test that waits for the whole process and then reads output cannot prove the first delta arrived early.
- `reasoning_content` is a DeepSeek extension. The fake server sends it, but a real model may omit it. The request fields are the acceptance evidence for enabling reasoning.
- A slow CI runner can stretch process startup, but the helper compares two monotonic timestamps inside the same process, so startup time cancels.
- The helper writes combined stdout and stderr. Do not assert on ordering between the token line and stderr.
