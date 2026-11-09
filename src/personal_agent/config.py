"""Runtime configuration loaded from the environment and the local .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MAX_STEPS = 20
REASONING_EFFORT = "high"


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    api_key: str
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    max_steps: int = DEFAULT_MAX_STEPS
    reasoning_effort: str = REASONING_EFFORT


def _load_dotenv() -> None:
    path = Path.cwd() / ".env"
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


def load_config(model: str | None = None) -> Config:
    _load_dotenv()

    api_key = os.environ.get("PA_API_KEY", "").strip()
    if not api_key:
        raise ConfigError("PA_API_KEY is not set. Copy .env.example to .env and fill in the key.")

    max_steps = _int("PA_MAX_STEPS", DEFAULT_MAX_STEPS)
    if max_steps < 1:
        raise ConfigError("PA_MAX_STEPS must be at least 1")

    return Config(
        api_key=api_key,
        model=(model or os.environ.get("PA_MODEL", "").strip() or DEFAULT_MODEL),
        base_url=os.environ.get("PA_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        max_steps=max_steps,
    )
