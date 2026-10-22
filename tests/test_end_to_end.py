"""End-to-end tests: real SDKs against a local fake HTTP server."""

from __future__ import annotations

import pytest

from assistant.config import Config
from assistant.messages import Message
from assistant.providers.anthropic_provider import AnthropicProvider
from assistant.providers.base import TextDelta, ThinkingDelta, TurnEnd
from assistant.providers.openai_provider import OpenAIProvider
from assistant.tools import default_registry
from tests.fake_server import serve


def make_config(provider: str, base_url: str) -> Config:
    return Config(
        provider=provider, api_key="k", base_url=base_url, model="m",
        max_tokens=100, max_steps=5, context_window=1000, show_usage=True,
    )


@pytest.fixture
def server():
    servers = []

    def start(protocol: str) -> str:
        instance, url = serve(protocol)
        servers.append(instance)
        return url

    yield start
    for instance in servers:
        instance.shutdown()


def test_openai_adapter_against_real_sdk(server):
    url = server("openai")
    provider = OpenAIProvider(make_config("openai", url + "/v1"))
    registry = default_registry(".")

    events = list(provider.stream([Message(role="user", text="read demo")], registry.specs))
    end = events[-1]

    assert isinstance(end, TurnEnd)
    assert end.usage.input_tokens == 42
    assert end.usage.output_tokens == 9
    assert len(end.message.tool_calls) == 1
    call = end.message.tool_calls[0]
    assert (call.id, call.name, call.arguments) == ("c1", "read", {"path": "demo.txt"})


def test_anthropic_adapter_against_real_sdk(server):
    url = server("anthropic")
    provider = AnthropicProvider(make_config("anthropic", url))
    registry = default_registry(".")

    events = list(provider.stream([Message(role="user", text="read demo")], registry.specs))
    end = events[-1]

    thinking = [e for e in events if isinstance(e, ThinkingDelta)]
    assert [e.text for e in thinking] == ["Need to read it."]

    assert isinstance(end, TurnEnd)
    assert end.stop_reason == "tool_use"
    assert end.usage.input_tokens == 37
    assert end.usage.output_tokens == 22

    block = end.message.thinking[0]
    assert block.text == "Need to read it."
    assert block.signature == "SIG-ABC"

    call = end.message.tool_calls[0]
    assert (call.id, call.name, call.arguments) == ("tu_1", "read", {"path": "demo.txt"})
