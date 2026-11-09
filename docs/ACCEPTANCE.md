# Acceptance criteria

The rebuild is accepted when the following behaviours are demonstrated. All
evidence is offline: the suite uses a local fake SSE server, a subprocess, and a
PTY, and never calls a real model API.

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | 正确调用 API | `tests/test_llm.py` asserts the request body against a local fake SSE server using the real SDK |
| 2 | 能在终端运行 | `tests/test_cli.py` starts the CLI in a subprocess and checks its exit code |
| 3 | 能通过 CLI 交互 | `tests/test_cli.py` drives the REPL through a PTY and asserts its output |
| 4 | 存在 SSE 流式 | `tests/test_llm.py` proves text deltas arrive before the stream ends |
| 5 | 模型能开启推理 | `tests/test_llm.py` asserts the request enables reasoning (`reasoning_effort` + `thinking`); no real-model test |
| 6 | 能调用工具 | `tests/test_agent.py` round-trips a fake tool call through bash and back into the next request |
