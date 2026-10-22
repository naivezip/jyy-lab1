from __future__ import annotations

from assistant.net import sanitize_proxy_env


def test_unbrackets_ipv6_entries(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,[::1],10.0.0.0/8")
    monkeypatch.setenv("no_proxy", "[::1]:8080")
    sanitize_proxy_env()
    import os

    assert os.environ["NO_PROXY"] == "localhost,::1,10.0.0.0/8"
    assert os.environ["no_proxy"] == "::1:8080"


def test_noop_without_brackets(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1")
    sanitize_proxy_env()
    import os

    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"


def test_idempotent(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "[::1]")
    monkeypatch.setenv("no_proxy", "[::1]")
    sanitize_proxy_env()
    sanitize_proxy_env()
    import os

    assert os.environ["NO_PROXY"] == "::1"


def test_anthropic_client_constructs(monkeypatch):
    from anthropic import Anthropic

    monkeypatch.setenv("NO_PROXY", "[::1]")
    monkeypatch.setenv("no_proxy", "[::1]")
    sanitize_proxy_env()
    client = Anthropic(api_key="k")
    assert str(client.base_url).startswith("https://api.anthropic.com")
