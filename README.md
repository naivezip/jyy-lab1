# personal-agent

[![CI](https://github.com/naivezip/jyy-lab1/actions/workflows/ci.yml/badge.svg)](https://github.com/naivezip/jyy-lab1/actions/workflows/ci.yml)

A minimal personal agent for the terminal: a ReAct loop over DeepSeek's
OpenAI-compatible API, streamed over SSE, with a single `bash` tool.

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

## How it works

- The agent runs a ReAct loop: stream one model step, execute the requested
  `bash` calls, feed the observations back, and repeat until the model stops
  calling tools or `PA_MAX_STEPS` is reached.
- Thinking is always enabled: requests send `reasoning_effort="high"` and
  `{"thinking": {"type": "enabled"}}`; `reasoning_content` is streamed dimmed and
  replayed on later turns.
- `bash` runs `bash -lc` in the current working directory, returns exit code,
  stdout and stderr, and truncates output at 16,000 characters. Commands run
  without confirmation, so only run `pa` in directories you trust.

## Development

```bash
make ci
```

The suite is fully offline: a local fake SSE server exercises the real `openai`
SDK, and a PTY drives the REPL. No real API key is needed for tests.
