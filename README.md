# pa

A local personal assistant and programming assistant for the terminal, built as a
small ReAct loop: the model streams a reply, calls tools, sees the results, and
continues until it has an answer.

Supports the **OpenAI Chat Completions** API (including DeepSeek, Qwen, vLLM and
other compatible gateways) and the **Anthropic Messages** API.

## Install

```bash
uv sync
uv tool install -e .   # puts `pa` on your PATH
```

## Configure

Copy `.env.example` to `.env` in the directory you work in, or to `~/.pa/.env`
to share one configuration everywhere:

```dotenv
PA_PROVIDER=openai        # or anthropic
PA_API_KEY=sk-...
PA_MODEL=gpt-5.5
# PA_BASE_URL=https://api.deepseek.com/v1
```

Real environment variables take precedence over `.env`. Optional settings:
`PA_MAX_TOKENS`, `PA_MAX_STEPS` (default 20), `PA_CONTEXT_WINDOW` (128000),
`PA_SHOW_USAGE` (1).

## Use

```bash
pa                    # interactive REPL
pa -c                 # resume the most recent session in this directory
pa -p "explain this repo"   # one-shot
```

Slash commands inside the REPL:

| Command | Effect |
| --- | --- |
| `/help` | list commands |
| `/new` | start a fresh session |
| `/sessions` | list sessions for this directory |
| `/compact` | summarise the conversation to free context |
| `/show [n]` | open the n-th most recent tool output in `$PAGER` |
| `/exit` | leave (Ctrl-D also works) |

## Tools

| Tool | What it does |
| --- | --- |
| `read` | read a text file with line numbers |
| `write` | write a file, creating parent directories |
| `bash` | run `bash -lc`, return exit code/stdout/stderr |
| `fd` | find files by regex or glob (pure Python, no binary needed) |
| `grep` | search file contents, print `path:line: text` |

Tool output is truncated at 16,000 characters before it enters the conversation.

## Context

- `SYSTEM.md` ships with the package and defines the assistant's behaviour.
- `AGENTS.md` files are collected from the working directory up to the git root
  (outside-in), so project rules closer to where you start take precedence.

## Sessions

Conversations are appended to
`~/.pa/projects/<sha1(cwd)[:12]>/sessions/<timestamp>-<id>.jsonl`.
Compaction appends a summary record instead of rewriting history, so the original
transcript stays auditable. When context grows past 80% of `PA_CONTEXT_WINDOW`
the conversation is compacted automatically; `/compact` does it on demand.

## Thinking

Thinking is requested by default and streamed dimmed in the terminal. On
Anthropic models that support adaptive thinking we ask for `display: "summarized"`;
models that reject adaptive thinking fall back to no thinking with a notice.
On OpenAI-compatible gateways `reasoning_content` is displayed and replayed
automatically.

## Development

```bash
uv run pytest
```
