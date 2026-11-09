"""Tests for environment and .env configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from personal_agent.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_STEPS,
    DEFAULT_MODEL,
    ConfigError,
    load_config,
)

PA_VARIABLES = ("PA_API_KEY", "PA_MODEL", "PA_BASE_URL", "PA_MAX_STEPS")


@pytest.fixture
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    original = dict(os.environ)
    monkeypatch.chdir(tmp_path)
    for name in PA_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    yield tmp_path
    os.environ.clear()
    os.environ.update(original)


def test_missing_api_key_is_rejected(clean_environment: Path) -> None:
    with pytest.raises(ConfigError, match="PA_API_KEY"):
        load_config()


def test_defaults(clean_environment: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PA_API_KEY", "key")

    config = load_config()

    assert config.api_key == "key"
    assert config.model == DEFAULT_MODEL
    assert config.base_url == DEFAULT_BASE_URL
    assert config.max_steps == DEFAULT_MAX_STEPS


def test_dotenv_is_loaded(clean_environment: Path) -> None:
    (clean_environment / ".env").write_text(
        "PA_API_KEY=file-key\nPA_MODEL=file-model\nPA_BASE_URL=http://file-host\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.api_key == "file-key"
    assert config.model == "file-model"
    assert config.base_url == "http://file-host"


def test_real_environment_wins_over_dotenv(
    clean_environment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (clean_environment / ".env").write_text(
        "PA_API_KEY=file-key\nPA_MODEL=file-model\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PA_MODEL", "env-model")

    assert load_config().model == "env-model"


def test_model_argument_wins(clean_environment: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PA_API_KEY", "key")
    monkeypatch.setenv("PA_MODEL", "env-model")

    assert load_config("cli-model").model == "cli-model"


def test_invalid_max_steps_is_rejected(
    clean_environment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PA_API_KEY", "key")
    monkeypatch.setenv("PA_MAX_STEPS", "0")

    with pytest.raises(ConfigError, match="PA_MAX_STEPS"):
        load_config()
