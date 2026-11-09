---
name: verify-agent-loop
description: "Formally verify the ReAct turn loop: every tool call gets exactly one tool response before the next model request, and a turn never exceeds PA_MAX_STEPS. Use when changing src/personal_agent/agent.py, tool-call handling, or the stream_step StepEnd contract."
---

# Verify the agent loop

**Property.** For every model response sequence in scope, each assistant message with N tool calls is followed by exactly N tool messages with matching ids and order before the next model request. A turn appends at most `Config.max_steps` assistant messages.

**Harm.** An unanswered tool call or an orphan tool message makes the next DeepSeek request replay an invalid message history. The API rejects that request and the user's turn fails. A broken step bound lets one prompt spend an unbounded number of model calls.

## Run

```bash
make verify-agent-loop
```

or `bash formal/agent-loop/run.sh`.

Two checks run:

1. **Real-code bounded exhaustive check.** `formal/agent-loop/verify_agent_loop.py` runs the real `Agent.run` for every sequence of 1 to 3 model steps drawn from five structural response shapes: final answer, one valid bash call, two valid bash calls, unknown tool, malformed JSON. That is 155 sequences. It checks the history passed to every `stream_step` request and the final history.
2. **TLA+ model.** `formal/agent-loop/AgentLoop.tla`, checked by TLC 2.19 from the bundled `tla2tools` 1.7.4 jar. Bounds: `MaxSteps = 3`, `MaxCalls = 2`, distinct call ids `{"c1", "c2"}`. Invariants: `ApiHistoryWellFormed`, `BoundedSteps`. Property: `EventuallyTerminal`.

Expected output ends with `verified 155 response sequences (max_steps 1..3)` and `Model checking completed. No error has been found.`

Read every TLA+ result with the pstack `/statechart` skill. A violation becomes its shortest path in plain words; a pass becomes a state chart of the loop.

## If it fails

- A Python `AssertionError` with `missing tool message`, `orphan message after tool call`, `tool id mismatch`, `step limit exceeded`, or `expected step-limit notice` is a real code bug. Report the failing response sequence in the code's terms: which model response, which call, which position in the history.
- A TLC `Invariant ... is violated` is a design counterexample. Read the trace with `/statechart`, then replay that sequence against the real code through the alphabet in `verify_agent_loop.py`. If the real Agent does not follow the trace, the model is wrong, not the code.
- Never weaken an invariant or remove a response kind to make the check pass.

## Coverage record

- Sync commit: `9219179` (HEAD at 2026-11-08). The covered files are uncommitted in this checkout, so confirm by hash as well as commit.
- `src/personal_agent/agent.py` sha256 `2b2999c3c7a73d9267511eb87b7fbced791d55f155f144c4a6535c556e6e45a4` covers `Agent.run`, `Agent._run_tool`, `Agent._rejected`.
- `src/personal_agent/llm.py` sha256 `50f7de696e6c0eda9c26790053afc74eff5d7b4e9f177d45abf5e45d9ace24e6` covers the `stream_step` contract: exactly one `StepEnd` whose message is an assistant message with optional `tool_calls`.
- `src/personal_agent/tools/bash.py` sha256 `59efd220ceba928340f2de6735754e46747d97548a44e86d2261708cee7600d2` covers the `BashTool.run` contract: one observation, never raises.
- `src/personal_agent/config.py` sha256 `84276106b172d7a653c69e1c49217deb36f74082f8951c4b957a956b5a90647e` covers `Config.max_steps` being at least 1.

When a covered file changes, rerun `make verify-agent-loop`. Confirm the model still describes the code. Then update the hash and sync commit here. Move the sync commit forward only after that confirmation.

## Scope

Covers structural history integrity and the step bound for bounded model responses. It does not cover the real DeepSeek API, network failures, prompt content, command semantics beyond `BashTool.run`'s one-observation contract, CLI rendering, or config parsing. The TLA+ model checks the abstract design at `MaxSteps = 3`, `MaxCalls = 2`, and distinct call ids. It is not a proof for unbounded conversations or arbitrary tool names.
