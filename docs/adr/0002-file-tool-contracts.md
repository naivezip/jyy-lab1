# File tools: workspace-confined read/write/edit

`pa` exposes `read`, `write`, and `edit` as first-class model tools alongside
`bash`. All three resolve paths inside the workspace and reject escapes:
relative and absolute paths are allowed only when their real target stays under
the workspace root, and symlinks are judged by their real target. `bash` keeps
the workspace as its working directory but remains deliberately unconfined. File
work is split by existence: `write` only creates new files, `edit` only modifies
existing files, and `edit` replaces a 1-based inclusive line range reported by
`read`; `read` therefore returns exact, stable line numbers.

Line-range editing was chosen over the more common exact-string replacement
because `read` already gives the model authoritative line numbers, and a range
schema keeps the smallest useful edit tool deterministic and easy to test. The
cost is that stale line numbers can corrupt an edit if the file changes between
`read` and `edit`; the current single-process CLI accepts that risk and
mitigates it with a "read before edit" system-prompt rule plus range
validation. The workspace boundary is a least-privilege default, not a sandbox:
because `bash` can still reach outside it, the boundary must not be presented as
a security guarantee.

## Consequences

- `write` fails when the target exists and directs the model to `edit`; `edit`
  fails when the target is missing and directs the model to `write`.
- Every file tool shares one path resolver; a future file tool must use it.
- `read` output is a contract: six-width line numbers plus a
  `lines a-b of N` header, with each line's original line ending preserved.
