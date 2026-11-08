# Acceptance criteria

The refactor is accepted when the following behaviours are demonstrated. CI
currently provides the lint and test harness; acceptance tests will be added
with the implementation.

| # | Criterion | Planned evidence |
| --- | --- | --- |
| 1 | 正确调用 API | Offline contract test against a local fake SSE server, exercising the real SDK |
| 2 | 能在终端运行 | Subprocess test that starts the CLI and checks its exit code |
| 3 | 能通过 CLI 交互 | PTY test that sends REPL commands and asserts the output |
| 4 | 存在 SSE 流式 | Fake server sends chunks incrementally; client emits deltas before the stream ends |
| 5 | 模型能开启推理 | Offline assertion that the request enables reasoning; manual real-model check with deepseek / deepseek-flash, outside CI |
| 6 | 能调用工具 | Fake server returns a tool call; test asserts execution and result round-trip |
