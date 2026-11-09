# Tests

The suite is fully offline. `tests/fake_server.py` is a local OpenAI-compatible
SSE server; `tests/test_llm.py` and `tests/test_agent.py` exercise the real
`openai` SDK against it, `tests/test_cli.py` drives the CLI in a subprocess and
through a PTY, and `tests/test_bash.py` covers the tool contract.

Run `make test` or `uv run pytest`.
