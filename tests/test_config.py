from __future__ import annotations

import pytest

from assistant.config import ConfigError, load_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in ("PA_PROVIDER", "PA_API_KEY", "PA_MODEL", "PA_BASE_URL",
                 "PA_MAX_TOKENS", "PA_MAX_STEPS", "PA_CONTEXT_WINDOW", "PA_SHOW_USAGE"):
        monkeypatch.delenv(name, raising=False)
    # Keep the developer's real ~/.pa/.env out of the tests.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)


def test_requires_api_key(monkeypatch):
    monkeypatch.setenv("PA_MODEL", "m")
    with pytest.raises(ConfigError, match="PA_API_KEY"):
        load_config()


def test_requires_model(monkeypatch):
    monkeypatch.setenv("PA_API_KEY", "k")
    with pytest.raises(ConfigError, match="PA_MODEL"):
        load_config()


def test_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("PA_API_KEY", "k")
    monkeypatch.setenv("PA_MODEL", "m")
    monkeypatch.setenv("PA_PROVIDER", "gemini")
    with pytest.raises(ConfigError, match="PA_PROVIDER"):
        load_config()


def test_defaults_per_provider(monkeypatch):
    monkeypatch.setenv("PA_API_KEY", "k")
    monkeypatch.setenv("PA_MODEL", "m")

    openai_cfg = load_config()
    assert openai_cfg.provider == "openai"
    assert openai_cfg.max_tokens == 8192
    assert openai_cfg.max_steps == 20
    assert openai_cfg.context_window == 128_000
    assert openai_cfg.base_url is None

    anthropic_cfg = load_config(provider="anthropic")
    assert anthropic_cfg.provider == "anthropic"
    assert anthropic_cfg.max_tokens == 16000


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("PA_API_KEY", "k")
    monkeypatch.setenv("PA_MODEL", "m")
    monkeypatch.setenv("PA_MAX_STEPS", "3")
    monkeypatch.setenv("PA_SHOW_USAGE", "0")
    monkeypatch.setenv("PA_BASE_URL", "https://example.test/v1")

    cfg = load_config()
    assert cfg.max_steps == 3
    assert cfg.show_usage is False
    assert cfg.base_url == "https://example.test/v1"


def test_bad_int(monkeypatch):
    monkeypatch.setenv("PA_API_KEY", "k")
    monkeypatch.setenv("PA_MODEL", "m")
    monkeypatch.setenv("PA_MAX_STEPS", "many")
    with pytest.raises(ConfigError, match="PA_MAX_STEPS"):
        load_config()
