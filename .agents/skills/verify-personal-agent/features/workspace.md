# Workspace boundary

The workspace is the directory tree the agent treats as home for file operations. Relative paths resolve from it, absolute paths are allowed only inside it, and paths whose real target is outside it are rejected before any file work happens.

## Sub-features

- `workspace-relative` resolves `notes.txt` from the workspace root.
- `workspace-absolute` accepts an absolute path that stays under the workspace root.
- `workspace-escape` rejects `../outside.txt` for read, write, and edit.
- `workspace-symlink` rejects a link inside the workspace whose real target is outside.
- `workspace-bash` starts bash commands in the workspace, but bash itself is deliberately not confined.

## How to get to it (user POV)

- Ask `pa` to read or write a file by relative path, for example `uv run pa -p "read notes.txt"`.
- Ask for a path outside the workspace and observe a rejection instead of a file operation.
- The model decides when to call a file tool. There is no separate user command for it.

## Driving it with pa_harness.py

Preconditions:

- `uv sync` has completed and `uv run pa-verify --json` reports six passes.
- The output directory is fresh.

- **Read by relative path.** Run `uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py read --path notes.txt --out artifacts/verify-personal-agent/<run-id>/workspace`. `output.txt` contains `read notes.txt` and `[read: lines 1-3 of 3]`; `files.json` shows only `notes.txt`.
- **Accept an absolute path inside the workspace.** Run the helper with `read --path notes.txt --absolute` and a fresh output directory. `output.txt` contains `[read: lines 1-3 of 3]`; the `argv.txt` command still records the readable relative path while the tool receives the workspace's absolute path.
- **Reject a symlink escape.** Run the helper with `read --path link.txt --symlink` and a fresh output directory. It creates `link.txt` pointing at a file outside the workspace. `output.txt` contains `[read: 'link.txt' resolves outside the workspace]`; `files.json` does not contain the outside target.
- **Reject a parent escape.** Run the helper with `--path ../outside.txt` and a fresh output directory. `output.txt` contains `[read: '../outside.txt' resolves outside the workspace]`; `files.json` still shows only the seeded workspace file. The rejection comes from the shared resolver before any file operation.
- **Reject a write escape.** Run `write --path ../outside.txt --content nope` with a fresh output directory. `output.txt` contains `[write: '../outside.txt' resolves outside the workspace]`; `exit_code.txt` reads `0` for the turn and `files.json` is empty.

## Gotchas

- The boundary applies to the file tools, not to `bash`. A bash command can still reach outside the workspace; do not describe the file boundary as a security sandbox.
- `write` and `edit` must fail before creating or changing anything on an escape. Assert `files.json`, not only the error text.
- Symlinks are judged by their real target; a link inside the workspace that points outside is rejected.
- Absolute paths are accepted only when the real target stays under the workspace root.
