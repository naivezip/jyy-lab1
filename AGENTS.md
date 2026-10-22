# Project rules for pa in this repository

- This repository is `pa-agent`, a Python 3.12 project managed with uv.
- Run tests with `uv run pytest`.
- Keep modules under `src/assistant/`; tests live in `tests/`.
- Provider-specific code belongs in `src/assistant/providers/`; nothing outside
  those adapters should import `openai` or `anthropic`.
- Tools live in `src/assistant/tools/` and must return a string; raise for errors.
