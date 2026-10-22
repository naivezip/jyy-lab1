"""Context compaction: summarise old turns and keep a short verbatim tail."""

from __future__ import annotations

import re

from assistant.messages import Message
from assistant.providers.base import Provider, ProviderError, TurnEnd

KEEP_TAIL = 4

COMPACT_PROMPT = """You compress conversation history for another assistant that will
continue the work. Produce a dense, structured summary with these sections:

## Goal
## Done
## Key files and paths
## Open questions
## Next step

Keep every file path, command, error message and decision that matters. Drop
chit-chat and reasoning. Reply with the summary only."""


def _transcript(messages: list[Message]) -> str:
    """A denoised view: no thinking blocks, but all text and tool traffic."""
    lines: list[str] = []
    for msg in messages:
        if msg.role == "system":
            continue
        if msg.role == "assistant":
            if msg.text:
                lines.append(f"ASSISTANT: {msg.text}")
            for call in msg.tool_calls:
                lines.append(f"TOOL CALL {call.name}({call.raw_arguments})")
        elif msg.role == "tool":
            for result in msg.tool_results:
                status = "ERROR" if result.is_error else "RESULT"
                lines.append(f"{status}: {result.content}")
        else:
            lines.append(f"USER: {msg.text or ''}")
    return "\n".join(lines)


def _strip_thinking(messages: list[Message]) -> list[Message]:
    return [
        Message(
            role=msg.role,
            text=msg.text,
            tool_calls=msg.tool_calls,
            tool_results=msg.tool_results,
        )
        for msg in messages
    ]


def _tail(messages: list[Message], keep: int = KEEP_TAIL) -> list[Message]:
    """Last few messages, advanced to a clean boundary.

    A tail must not start with a tool result or a dangling tool call: Anthropic
    and OpenAI both reject orphaned tool traffic.
    """
    start = max(0, len(messages) - keep)
    while start < len(messages):
        msg = messages[start]
        if msg.role == "tool" or (msg.role == "assistant" and msg.tool_calls):
            start += 1
            continue
        break
    return messages[start:]


def summarize(provider: Provider, history: list[Message]) -> str:
    transcript = _transcript(history)
    request = [
        Message(role="system", text=COMPACT_PROMPT),
        Message(role="user", text=f"Conversation so far:\n\n{transcript}"),
    ]
    end = None
    for event in provider.stream(request, []):
        if isinstance(event, TurnEnd):
            end = event
    if end is None or not end.message.text:
        raise ProviderError("Compaction returned an empty summary")
    return end.message.text


def compact(provider: Provider, history: list[Message]) -> list[Message]:
    """Return a shortened history. Original messages stay untouched on disk."""
    system = [msg for msg in history if msg.role == "system"]
    body = [msg for msg in history if msg.role != "system"]
    summary = summarize(provider, body)
    rebuilt = system + [Message(role="user", text=f"Summary of the earlier conversation:\n\n{summary}")]
    rebuilt += _strip_thinking(_tail(body))
    return rebuilt


CONTEXT_ERROR_MARKERS = ("context length", "context_length", "too many tokens",
                          "maximum context", "context window", "prompt is too long")


def is_context_overflow(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in CONTEXT_ERROR_MARKERS)


def estimate_overflow(usage_input: int, context_window: int, threshold: float = 0.8) -> bool:
    return context_window > 0 and usage_input >= context_window * threshold
