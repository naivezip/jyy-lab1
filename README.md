# personal-agent

[![CI](https://github.com/naivezip/jyy-lab1/actions/workflows/ci.yml/badge.svg)](https://github.com/naivezip/jyy-lab1/actions/workflows/ci.yml)

A minimal personal agent for the terminal: a ReAct loop over DeepSeek's
OpenAI-compatible API, streamed over SSE, with `bash` plus workspace-confined
`read`, `write`, and `edit` tools.

## Requirements

Python 3.12 or newer, managed with [uv](https://docs.astral.sh/uv/).

## Install

```bash
uv sync
uv run pa --version
```

To put `pa` on your `PATH`:

```bash
uv tool install -e .
```

## Configure

Copy `.env.example` to `.env` in the directory where you run `pa`, or export the
variables yourself. Real environment variables take precedence over `.env`.

| Variable | Required | Default |
| --- | --- | --- |
| `PA_API_KEY` | yes | — |
| `PA_MODEL` | no | `deepseek-flash` |
| `PA_BASE_URL` | no | `https://api.deepseek.com` |
| `PA_MAX_STEPS` | no | `20` |

## Use

```bash
pa                          # interactive REPL
pa -p "explain this repo"   # one-shot, then exit
pa --model deepseek         # override the model for this run
```

Inside the REPL:

| Command | Effect |
| --- | --- |
| `/help` | list commands |
| `/new` | clear the conversation |
| `/exit` | leave (Ctrl-D also works) |

Every answer ends with the token usage of that turn.

## Verify

`pa-verify` executes the six acceptance criteria in
[`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) against the real `pa` CLI. It runs
entirely offline: every check starts a local fake SSE server, uses a fresh
temporary workspace, and injects a fake API key, so no real key or network
access is needed.

```bash
uv run pa-verify
uv run pa-verify --list
uv run pa-verify --only repl,tool-roundtrip --json
```

| Flag | Effect |
| --- | --- |
| `--list` | list check ids, criteria, and titles without running anything |
| `--only ID[,ID]` | run only the named checks; repeatable, results keep registry order |
| `--json` | emit one JSON report on stdout |
| `--timeout SECONDS` | per-process timeout (default 30, must be positive) |
| `--version` | print `pa-verify 0.1.0` and exit |
| `--help` | show usage and exit |

Exit codes: `0` when every selected check passes, `1` when any check fails,
`2` for a usage error.

## How it works

- The agent runs a ReAct loop: stream one model step, execute the requested
  `bash`, `read`, `write`, or `edit` calls, feed the observations back, and repeat
  until the model stops calling tools or `PA_MAX_STEPS` is reached.
- Thinking is always enabled: requests send `reasoning_effort="high"` and
  `{"thinking": {"type": "enabled"}}`; `reasoning_content` is streamed dimmed and
  replayed on later turns.
- `bash` runs `bash -lc` in the current working directory, returns exit code,
  stdout and stderr, and truncates output at 16,000 characters. Commands run
  without confirmation, so only run `pa` in directories you trust.
- `read` returns a `lines a-b of N` header plus six-width numbered lines and can
  page by a 1-based inclusive line range. `write` only creates new files;
  `edit` only replaces a line range in an existing file. All three resolve paths
  inside the workspace and reject escapes, including symlinks whose real target
  is outside. The boundary is not a sandbox because `bash` remains unconfined.

## Development

```bash
make ci
```

The suite is fully offline: a local fake SSE server exercises the real `openai`
SDK, and a PTY drives the REPL. No real API key is needed for tests.
