# CLI basics

The CLI exposes version and help without a model call, and it reports a configuration error when the required API key is missing.

## Sub-features

- `cli-version` prints `pa 0.1.0` and exits 0.
- `cli-help` prints the usage line and exits 0.
- `cli-config-error` exits 2 and names `PA_API_KEY` when no key is configured.

## How to get to it (user POV)

- Run `uv run pa --version` from the repository root.
- Run `uv run pa --help` to see the flags.
- Run `uv run pa -p hi` with `PA_API_KEY` unset.

## Driving it with pa_harness.py

Preconditions:

- `uv sync` has completed.
- `pa-verify` is available from the installed package.
- The repository root has no `.env` file that supplies `PA_API_KEY` for the config-error command.

- **Version.** Run `uv run pa --version`. Exit code is `0` and stdout is exactly `pa 0.1.0`.
- **Help.** Run `uv run pa --help`. Exit code is `0` and stdout begins with `usage: pa`. The output lists `-p`, `--model`, and `--version`.
- **Acceptance check.** Run `uv run pa-verify --only cli-terminal --json`. Exit code is `0`, `"ok": true`, and the one result has `"status": "pass"` with `version: pa 0.1.0` and a `usage: pa` help line in evidence.
- **Missing key.** Run `env -u PA_API_KEY uv run pa -p hi`. Exit code is `2` and stderr contains `PA_API_KEY is not set`. Do not run this from a directory with a `.env` that contains a key.

## Gotchas

- `--version` and `--help` exit before configuration loading, so they work without a key.
- `pa-verify` injects a fake key and never reads a real key from the caller.
- A `.env` in the current working directory can supply `PA_API_KEY` and defeat the missing-key proof. Check the precondition before changing the result.
- The help output is argparse-owned. Assert the stable `usage: pa` substring rather than the full option order.
