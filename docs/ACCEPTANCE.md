# Acceptance criteria

The rebuild is accepted when the following behaviours are demonstrated. All
evidence is offline: the suite uses a local fake SSE server, a subprocess, and a
PTY, and never calls a real model API.

`uv run pa-verify` executes all ten rows below offline against the real CLI. It
needs no API key and no network access, runs every check in a fresh temporary
workspace against a local fake SSE server, and exits 0 only when all selected
checks pass. Run `uv run pa-verify --list` for the check ids.

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | 正确调用 API | `tests/test_llm.py` asserts the request body against a local fake SSE server using the real SDK |
| 2 | 能在终端运行 | `tests/test_cli.py` starts the CLI in a subprocess and checks its exit code |
| 3 | 能通过 CLI 交互 | `tests/test_cli.py` drives the REPL through a PTY and asserts its output |
| 4 | 存在 SSE 流式 | `tests/test_llm.py` proves text deltas arrive before the stream ends |
| 5 | 模型能开启推理 | `tests/test_llm.py` asserts the request enables reasoning (`reasoning_effort` + `thinking`); no real-model test |
| 6 | 能调用工具 | `tests/test_agent.py` round-trips a fake tool call through bash and back into the next request |
| 7 | 能读取文件 | `pa-verify --only read-tool` drives a `read` call and asserts the `lines a-b of N` header and numbered lines |
| 8 | 能创建文件 | `pa-verify --only write-tool` creates a file and asserts that an existing target is refused with a pointer to `edit` |
| 9 | 能编辑文件 | `pa-verify --only edit-tool` replaces a line range and asserts the resulting file content |
| 10 | 文件工具受工作区限制 | `pa-verify --only workspace-boundary` rejects read and write escapes and asserts no outside file appears |
