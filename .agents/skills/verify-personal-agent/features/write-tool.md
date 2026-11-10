# Write tool

The write tool lets the model create a new text file in the workspace, including missing parent directories, without ever modifying a file that already exists.

## Sub-features

- `write-create` creates a new file with exact UTF-8 content.
- `write-parents` creates missing parent directories.
- `write-existing` refuses an existing target and directs the model to `edit`.
- `write-boundary` rejects paths that resolve outside the workspace.

## How to get to it (user POV)

- Ask `pa` to create a file, for example `uv run pa -p "create created.txt with a verification marker"`.
- Watch the `write <path>` line and the `[write: Wrote N bytes to <path>]` summary in the terminal.
- The model decides when to call the tool. There is no separate user command for it.

## Driving it with pa_harness.py

Preconditions:

- `uv sync` has completed and `uv run pa-verify --json` reports ten passes.
- The output directory is fresh.

- **Create a file.** Run `uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py write --path created.txt --content "created by write\n" --out artifacts/verify-personal-agent/<run-id>/write-tool`. `output.txt` contains `write created.txt`, `[write: Wrote 17 bytes to created.txt]`, and `Done.`; `exit_code.txt` reads `0`.
- **Create a nested file.** Run the helper with `--path deep/nested/created.txt` and a fresh output directory. `files.json` contains `"deep/nested/created.txt": "created by write\n"`, proving the missing parent directories were created.
- **Confirm the side effect.** `artifact.txt` contains `created by write`, and `files.json` contains `"created.txt": "created by write\n"`. This is a second user-facing view of the file, not only the renderer summary.
- **Confirm the model saw the observation.** `requests.json` contains exactly two requests. The second request contains an assistant `tool_calls` entry for `call_1` followed by a `role: "tool"` message with `tool_call_id: "call_1"` and content containing `Wrote 17 bytes`.
- **Try an existing target.** Run the helper with `--path notes.txt --seed "notes.txt=alpha\n"` and a fresh output directory. `output.txt` contains `[write: notes.txt already exists; use edit to modify an existing file]`; `files.json` still shows `"notes.txt": "alpha\n"`.

## Gotchas

- `write` is create-only. An existing file is an error even when the content is identical; use `edit` instead.
- The workspace is a temporary directory owned by the helper. Relative paths resolve there, not in the repository.
- A successful write creates missing parent directories; asserting only the message without reading `files.json` is insufficient proof.
- A path such as `../outside.txt` is rejected before any file is created.
