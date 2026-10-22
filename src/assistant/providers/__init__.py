"""Provider selection."""

from __future__ import annotations

from assistant.config import Config
from assistant.net import sanitize_proxy_env
from assistant.providers.base import Provider


def build_provider(config: Config) -> Provider:
    sanitize_proxy_env()
    if config.provider == "openai":
        from assistant.providers import openai_provider

        return openai_provider.build(config)
    if config.provider == "anthropic":
        from assistant.providers import anthropic_provider

        return anthropic_provider.build(config)
    raise ValueError(f"unknown provider: {config.provider}")
