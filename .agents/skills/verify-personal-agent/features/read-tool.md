# Read tool

The read tool lets the model inspect a text file in the workspace as numbered lines, page through a line range, and feed the exact file contents back into the next model step.

## Sub-features

- `read-whole` returns the first 2000 lines of a file with a `lines a-b of N` header.
- `read-range` pages with a 1-based inclusive `start`/`end` pair.
- `read-format` prefixes every line with a six-width line number and preserves its original line ending.
- `read-error` returns a missing, non-file, or non-UTF-8 path as an observation instead of crashing the turn.

## How to get to it (user POV)

- Ask `pa` to read or inspect a file, for example `uv run pa -p "read notes.txt and summarise it"`.
- Watch the `read <path>` line and the `[read: lines a-b of N]` summary in the terminal.
- The model decides when to call the tool. There is no separate user command for it.

## Driving it with pa_harness.py

Preconditions:

- `uv sync` has completed and `uv run pa-verify --json` reports ten passes.
- The workspace is the helper's fresh temporary directory.
- The output directory is fresh.

- **Read a whole file.** Run `uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py read --path notes.txt --out artifacts/verify-personal-agent/<run-id>/read-tool`. The helper seeds `notes.txt` with three lines, then serves a `read` call and a final reply. `output.txt` contains `read notes.txt`, `[read: lines 1-3 of 3]`, and `Done.`; `exit_code.txt` reads `0`.
- **Page a range.** Run the helper with `--start 2 --end 3` and a fresh output directory. `output.txt` contains `[read: lines 2-3 of 3]`; `requests.json` contains exactly two requests and the second request has a `role: "tool"` message whose content starts with `lines 2-3 of 3`.
- **Confirm the exact text.** `files.json` contains `"notes.txt": "alpha\nbeta\ngamma\n"`, and `artifact.txt` contains the same three lines. The read observation preserves the source text and its line endings.

## Gotchas

- The header is part of the contract: assert `lines a-b of N`, not only the numbered lines.
- `start` and `end` are 1-based and inclusive. `end` defaults to 2000 lines from `start`.
- The workspace is a temporary directory owned by the helper. Relative paths resolve there, not in the repository.
- A binary or non-UTF-8 file is an observation with `is_error=True`; do not treat it as a successful read.
