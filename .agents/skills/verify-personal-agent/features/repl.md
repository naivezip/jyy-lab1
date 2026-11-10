# Interactive REPL

The REPL lets a user keep one conversation open in a terminal, send multiple prompts, use slash commands, and leave with `/exit` or Ctrl-D.

## Sub-features

- `repl-start` prints the version, model, working directory, and prompt hint.
- `repl-chat` sends a prompt and prints the streamed answer with token usage.
- `repl-help` lists `/help`, `/new`, and `/exit`.
- `repl-new` clears the conversation while keeping the session alive.
- `repl-exit` leaves with status 0.

## How to get to it (user POV)

- Run `uv run pa` from the repository root. The prompt is `>`.
- Type `/help` to list commands.
- Type `/new` to clear the conversation.
- Type `/exit` or press Ctrl-D to leave.

## Driving it with pa_harness.py

Preconditions:

- `uv sync` has completed and `uv run pa-verify --json` reports ten passes.
- For a direct `uv run pa`, `PA_API_KEY` is available from the environment or the current directory's `.env`; without it, `pa` exits 2 before printing the banner. `pa_harness.py` injects `PA_API_KEY=verify-key` for the journey.
- The helper has a PTY available. The app uses `input()` and the renderer checks `isatty()`.
- The output directory is fresh.

- **Start the REPL.** Run `uv run python .agents/skills/verify-personal-agent/scripts/pa_harness.py repl --prompt hello --reply "Hello from the verification model." --out artifacts/verify-personal-agent/<run-id>/repl`. `transcript.txt` contains `pa 0.1.0`, `deepseek-flash`, `Type /help for commands.`, and the `>` prompt; `exit_code.txt` reads `0`.
- **Use help.** The helper sends `/help\n` after the banner. `transcript.txt` contains `Commands:` and the three command names.
- **Chat.** The helper sends `hello\n` after `/help`. The transcript contains `Hello from the verification model.` and `[tokens] input=10 output=2`.
- **Start a new conversation.** The helper sends `/new\n`. The transcript contains `New conversation.` after the reply and usage line.
- **Exit cleanly.** The helper sends `/exit\n`, reads to end of file, and records the exit status. `exit_code.txt` is `0` and `requests.json` contains one request for the single user turn.

## Gotchas

- The REPL needs a PTY because the helper sends keystrokes and the renderer checks `isatty()` for dimming. `input()` flushes stdout before reading, so a plain pipe still receives the banner; a pipe cannot be driven with `send()`.
- PTY output contains echoed input and ANSI dim codes. Assert on short byte substrings, not whole lines.
- `/help` and `/new` do not call the model. `requests.json` should contain only the one request from `hello`.
- `/new` keeps the system message and drops the rest of the history. The transcript proving `New conversation.` is not proof that the next turn has no history; a second turn is needed for that.
- Ctrl-D exits with status 0 and prints a newline. The helper uses `/exit` for deterministic cleanup.
