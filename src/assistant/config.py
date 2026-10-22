"""Runtime configuration, loaded from the environment (and .env files)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROVIDERS = ("openai", "anthropic")

# Anthropic counts thinking tokens against max_tokens; OpenAI-compatible
# gateways use it as a hard completion cap. Different sensible defaults.
DEFAULT_MAX_TOKENS = {"openai": 8192, "anthropic": 16000}


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    provider: str
    api_key: str
    base_url: str | None
    model: str
    max_tokens: int
    max_steps: int
    context_window: int
    show_usage: bool


def _load_env_files() -> None:
    """Load .env from cwd first, then ~/.pa/.env. Real env vars always win."""
    for path in (Path.cwd() / ".env", Path.home() / ".pa" / ".env"):
        if path.is_file():
            load_dotenv(path, override=False)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def load_config(provider: str | None = None) -> Config:
    _load_env_files()

    name = (provider or os.environ.get("PA_PROVIDER", "") or "openai").strip().lower()
    if name not in PROVIDERS:
        raise ConfigError(f"PA_PROVIDER must be one of {PROVIDERS}, got {name!r}")

    api_key = os.environ.get("PA_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "PA_API_KEY is not set. Copy .env.example to .env (in this directory "
            "or ~/.pa/.env) and fill in PA_API_KEY, PA_MODEL and PA_PROVIDER."
        )

    model = os.environ.get("PA_MODEL", "").strip()
    if not model:
        raise ConfigError("PA_MODEL is not set (e.g. PA_MODEL=gpt-5.5).")

    return Config(
        provider=name,
        api_key=api_key,
        base_url=os.environ.get("PA_BASE_URL", "").strip() or None,
        model=model,
        max_tokens=_int("PA_MAX_TOKENS", DEFAULT_MAX_TOKENS[name]),
        max_steps=_int("PA_MAX_STEPS", 20),
        context_window=_int("PA_CONTEXT_WINDOW", 128_000),
        show_usage=os.environ.get("PA_SHOW_USAGE", "1").strip() not in ("0", "false", "no"),
    )
