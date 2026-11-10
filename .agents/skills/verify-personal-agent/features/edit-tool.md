# Edit tool

The edit tool lets the model replace a 1-based inclusive line range in an existing text file, using the stable line numbers returned by the read tool.

## Sub-features

- `edit-replace` replaces the selected lines with the supplied content.
- `edit-range` validates a 1-based inclusive `start`/`end` pair against the file's line count.
- `edit-missing` refuses a missing target and directs the model to `write`.
- `edit-preserve` keeps the file's existing line-ending style.

## How to get to it (user POV)

- Ask `pa` to change part of an existing file, for example `uv run pa -p "change line 2 of notes.txt to BETA"`.
- Watch the `edit <path>` line and the `[edit: Edited <path>: replaced lines a-b of N]` summary in the terminal.
- The model decides when to call the tool. There is no separate user command for it.

## Driving it with pa_harness.py

Preconditions:

- `uv sync` has completed and `uv run pa-verify --json` reports six passes.
- The output directory is fresh.

- **Replace one line.** Run `uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py edit --path notes.txt --start 2 --end 2 --content "BETA\n" --out artifacts/verify-personal-agent/<run-id>/edit-tool`. The helper seeds `notes.txt` with `alpha`, `beta`, `gamma`, serves an `edit` call, and then a final reply. `output.txt` contains `edit notes.txt`, `[edit: Edited notes.txt: replaced lines 2-2 of 3]`, and `Done.`; `exit_code.txt` reads `0`.
- **Confirm the side effect.** `artifact.txt` and `files.json` both show `"alpha\nBETA\ngamma\n"`. A second read of the file, not only the renderer message, is the proof that the range was replaced.
- **Confirm the model saw the observation.** `requests.json` contains exactly two requests; the second request's `role: "tool"` message for `call_1` contains `Edited notes.txt`.
- **Try a missing target.** Run the helper with `--path missing.txt --seed "notes.txt=alpha\n"` and a fresh output directory. `output.txt` contains `[edit: missing.txt does not exist; use write to create a new file]`; `exit_code.txt` remains `0` for the overall turn.

## Gotchas

- The range is 1-based and inclusive. An `end` before `start` or past the last line is an observation error.
- `edit` only modifies an existing file. A missing file is an error that points to `write`.
- The workspace is a temporary directory owned by the helper. Relative paths resolve there, not in the repository.
- A stale line range can corrupt an edit if the file changes between the read and the edit; the model must read before editing.
