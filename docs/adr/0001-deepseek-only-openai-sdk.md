# DeepSeek-only via the OpenAI SDK

The agent targets a single provider: DeepSeek's OpenAI-compatible Chat
Completions API, accessed through the official `openai` Python SDK. The
acceptance contract requires the real SDK and DeepSeek's `deepseek` /
`deepseek-flash` models, while a second provider would add a translation layer
with no user-visible benefit at this stage.

As a consequence, conversation history is stored directly in OpenAI wire format
(`role`, `content`, `reasoning_content`, `tool_calls`, `tool_call_id`); there is
no provider-neutral message model. Supporting another provider later means
introducing an adapter boundary around `llm.py` and `agent.py`, not changing
configuration alone.

## Consequences

- `reasoning_content` is preserved on every assistant message and replayed
  whenever the request carries `tools`, as DeepSeek requires.
- Tests exercise the real SDK against a local fake SSE server; no real API calls
  run in CI.
