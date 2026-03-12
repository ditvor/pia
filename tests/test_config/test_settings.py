"""Tests for the configuration loader and settings models."""

from __future__ import annotations

import pathlib

import pytest
import yaml
from pydantic import ValidationError

from pia.config.defaults import (
    DEFAULT_EXCLUDE_PATTERNS,
    DEFAULT_GIT_HISTORY_DAYS,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_SYNC_INTERVAL,
)
from pia.config.settings import (
    Settings,
    _apply_env_vars,
    _deep_merge,
    _interpolate_env_refs,
    load_settings,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_ENV = {
    "YOUTRACK_URL": "https://test.youtrack.cloud",
    "YOUTRACK_TOKEN": "test-token",
    "ANTHROPIC_API_KEY": "test-api-key",
}


def _write_yaml(path: pathlib.Path, data: dict) -> pathlib.Path:
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _deep_merge
# ---------------------------------------------------------------------------


def test_deep_merge_simple_override():
    result = _deep_merge({"a": 1, "b": 2}, {"b": 99, "c": 3})
    assert result == {"a": 1, "b": 99, "c": 3}


def test_deep_merge_nested_dicts_are_merged_not_replaced():
    base = {"youtrack": {"url": "https://base.example.com", "token": "tok"}}
    override = {"youtrack": {"url": "https://new.example.com"}}
    result = _deep_merge(base, override)
    assert result["youtrack"]["url"] == "https://new.example.com"
    # token from base should survive
    assert result["youtrack"]["token"] == "tok"


def test_deep_merge_does_not_mutate_base():
    base = {"a": {"b": 1}}
    _deep_merge(base, {"a": {"c": 2}})
    assert "c" not in base["a"]


def test_deep_merge_non_dict_value_replaces_dict():
    # If override provides a non-dict where base had a dict, replace it.
    result = _deep_merge({"x": {"nested": True}}, {"x": "flat"})
    assert result["x"] == "flat"


# ---------------------------------------------------------------------------
# _interpolate_env_refs
# ---------------------------------------------------------------------------


def test_interpolate_replaces_known_var(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "abc123")
    assert _interpolate_env_refs("${MY_SECRET}") == "abc123"


def test_interpolate_unknown_var_becomes_empty_string(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    assert _interpolate_env_refs("${MISSING_VAR}") == ""


def test_interpolate_nested_dict(monkeypatch):
    monkeypatch.setenv("THE_TOKEN", "tok")
    data = {"youtrack": {"token": "${THE_TOKEN}", "url": "https://x.com"}}
    result = _interpolate_env_refs(data)
    assert result["youtrack"]["token"] == "tok"
    assert result["youtrack"]["url"] == "https://x.com"


def test_interpolate_list_values(monkeypatch):
    monkeypatch.setenv("PROJ_A", "PROJ")
    result = _interpolate_env_refs(["${PROJ_A}", "HD"])
    assert result == ["PROJ", "HD"]


def test_interpolate_non_string_values_unchanged():
    assert _interpolate_env_refs(42) == 42
    assert _interpolate_env_refs(True) is True
    assert _interpolate_env_refs(None) is None


# ---------------------------------------------------------------------------
# _apply_env_vars
# ---------------------------------------------------------------------------


def test_apply_env_vars_youtrack(monkeypatch):
    monkeypatch.setenv("YOUTRACK_URL", "https://yt.example.com")
    monkeypatch.setenv("YOUTRACK_TOKEN", "my-tok")
    result = _apply_env_vars({})
    assert result["youtrack"]["url"] == "https://yt.example.com"
    assert result["youtrack"]["token"] == "my-tok"


def test_apply_env_vars_anthropic_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = _apply_env_vars({})
    assert result["llm"]["api_key"] == "ant-key"


def test_apply_env_vars_openai_api_key_when_provider_openai(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = _apply_env_vars({})
    assert result["llm"]["api_key"] == "oai-key"


def test_apply_env_vars_llm_api_key_overrides_provider_specific(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "generic-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")
    result = _apply_env_vars({})
    assert result["llm"]["api_key"] == "generic-key"


def test_apply_env_vars_youtrack_projects_comma_separated(monkeypatch):
    monkeypatch.setenv("YOUTRACK_PROJECTS", "PROJ, HD, INTERNAL")
    result = _apply_env_vars({})
    assert result["youtrack"]["projects"] == ["PROJ", "HD", "INTERNAL"]


def test_apply_env_vars_numeric_coercion(monkeypatch):
    monkeypatch.setenv("LLM_MAX_TOKENS", "2048")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.2")
    monkeypatch.setenv("CODEBASE_GIT_HISTORY_DAYS", "30")
    monkeypatch.setenv("YOUTRACK_SYNC_INTERVAL", "600")
    result = _apply_env_vars({})
    assert result["llm"]["max_tokens"] == 2048
    assert result["llm"]["temperature"] == pytest.approx(0.2)
    assert result["codebase"]["git_history_days"] == 30
    assert result["youtrack"]["sync_interval"] == 600


def test_apply_env_vars_does_not_mutate_input(monkeypatch):
    monkeypatch.setenv("YOUTRACK_URL", "https://x.com")
    original = {}
    _apply_env_vars(original)
    assert original == {}


def test_apply_env_vars_unset_vars_leave_keys_absent(monkeypatch):
    for key in ("YOUTRACK_URL", "YOUTRACK_TOKEN", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    result = _apply_env_vars({})
    assert "url" not in result.get("youtrack", {})
    assert "token" not in result.get("youtrack", {})
    assert "api_key" not in result.get("llm", {})


# ---------------------------------------------------------------------------
# load_settings — all required values from env
# ---------------------------------------------------------------------------


def test_load_settings_all_from_env(monkeypatch, tmp_path):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = load_settings(tmp_path / "nonexistent.yaml")
    assert settings.youtrack.url == "https://test.youtrack.cloud"
    assert settings.youtrack.token == "test-token"
    assert settings.llm.api_key == "test-api-key"


def test_load_settings_applies_defaults(monkeypatch, tmp_path):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = load_settings(tmp_path / "nonexistent.yaml")
    assert settings.llm.provider == DEFAULT_LLM_PROVIDER
    assert settings.llm.model == DEFAULT_LLM_MODEL
    assert settings.llm.max_tokens == DEFAULT_LLM_MAX_TOKENS
    assert settings.llm.temperature == pytest.approx(DEFAULT_LLM_TEMPERATURE)
    assert settings.youtrack.sync_interval == DEFAULT_SYNC_INTERVAL
    assert settings.codebase.git_history_days == DEFAULT_GIT_HISTORY_DAYS
    assert settings.codebase.exclude_patterns == DEFAULT_EXCLUDE_PATTERNS


# ---------------------------------------------------------------------------
# load_settings — YAML file
# ---------------------------------------------------------------------------


def test_load_settings_from_yaml(monkeypatch, tmp_path):
    for k in _REQUIRED_ENV:
        monkeypatch.delenv(k, raising=False)

    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {
        "youtrack": {"url": "https://yaml.youtrack.cloud", "token": "yaml-tok"},
        "llm": {"provider": "anthropic", "api_key": "yaml-api-key"},
    })
    settings = load_settings(cfg)
    assert settings.youtrack.url == "https://yaml.youtrack.cloud"
    assert settings.youtrack.token == "yaml-tok"
    assert settings.llm.api_key == "yaml-api-key"


def test_load_settings_yaml_env_interpolation(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTRACK_TOKEN", "env-tok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-api")

    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {
        "youtrack": {"url": "https://x.youtrack.cloud", "token": "${YOUTRACK_TOKEN}"},
        "llm": {"provider": "anthropic", "api_key": "${ANTHROPIC_API_KEY}"},
    })
    settings = load_settings(cfg)
    assert settings.youtrack.token == "env-tok"
    assert settings.llm.api_key == "env-api"


def test_load_settings_env_overrides_yaml(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTRACK_TOKEN", "env-wins")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-api-wins")

    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {
        "youtrack": {"url": "https://x.youtrack.cloud", "token": "yaml-tok"},
        "llm": {"api_key": "yaml-api-key"},
    })
    settings = load_settings(cfg)
    assert settings.youtrack.token == "env-wins"
    assert settings.llm.api_key == "env-api-wins"


def test_load_settings_yaml_custom_fields(monkeypatch, tmp_path):
    for k in _REQUIRED_ENV:
        monkeypatch.delenv(k, raising=False)

    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {
        "youtrack": {
            "url": "https://x.youtrack.cloud",
            "token": "tok",
            "projects": ["PROJ", "HD"],
            "sync_interval": 600,
        },
        "llm": {
            "provider": "anthropic",
            "api_key": "key",
            "model": "claude-opus-4-6",
            "max_tokens": 2048,
            "temperature": 0.0,
        },
        "codebase": {
            "root": "/repo",
            "git_history_days": 30,
            "exclude_patterns": ["dist/"],
        },
        "database": {"path": "/tmp/test.db"},
    })
    settings = load_settings(cfg)
    assert settings.youtrack.projects == ["PROJ", "HD"]
    assert settings.youtrack.sync_interval == 600
    assert settings.llm.model == "claude-opus-4-6"
    assert settings.llm.max_tokens == 2048
    assert settings.llm.temperature == pytest.approx(0.0)
    assert settings.codebase.root == "/repo"
    assert settings.codebase.git_history_days == 30
    assert settings.codebase.exclude_patterns == ["dist/"]
    assert "/tmp/test.db" in settings.database.path


# ---------------------------------------------------------------------------
# load_settings — validation errors
# ---------------------------------------------------------------------------


def test_load_settings_missing_youtrack_url_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("YOUTRACK_URL", raising=False)
    monkeypatch.setenv("YOUTRACK_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    with pytest.raises(ValidationError) as exc_info:
        load_settings(tmp_path / "none.yaml")
    assert "url" in str(exc_info.value)


def test_load_settings_missing_token_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTRACK_URL", "https://x.youtrack.cloud")
    monkeypatch.delenv("YOUTRACK_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    with pytest.raises(ValidationError) as exc_info:
        load_settings(tmp_path / "none.yaml")
    assert "token" in str(exc_info.value)


def test_load_settings_missing_api_key_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTRACK_URL", "https://x.youtrack.cloud")
    monkeypatch.setenv("YOUTRACK_TOKEN", "tok")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        load_settings(tmp_path / "none.yaml")
    assert "api_key" in str(exc_info.value)


def test_load_settings_invalid_provider_raises(monkeypatch, tmp_path):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("LLM_PROVIDER", "cohere")
    with pytest.raises(ValidationError):
        load_settings(tmp_path / "none.yaml")


def test_load_settings_invalid_temperature_raises(monkeypatch, tmp_path):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("LLM_TEMPERATURE", "1.5")
    with pytest.raises(ValidationError):
        load_settings(tmp_path / "none.yaml")


# ---------------------------------------------------------------------------
# Individual model validators
# ---------------------------------------------------------------------------


def test_youtrack_url_trailing_slash_stripped():
    s = Settings.model_validate({
        "youtrack": {"url": "https://x.youtrack.cloud/", "token": "t"},
        "llm": {"api_key": "k"},
    })
    assert not s.youtrack.url.endswith("/")


def test_database_path_tilde_expanded(monkeypatch, tmp_path):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = load_settings(tmp_path / "none.yaml")
    # Default path contains ~/.pia/graph.db; ~ must be expanded.
    assert "~" not in settings.database.path
    assert pathlib.Path(settings.database.path).is_absolute()


def test_database_resolved_property(monkeypatch, tmp_path):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = load_settings(tmp_path / "none.yaml")
    assert isinstance(settings.database.resolved, pathlib.Path)
    assert settings.database.resolved.is_absolute()


def test_git_history_days_negative_raises():
    with pytest.raises(ValidationError):
        Settings.model_validate({
            "youtrack": {"url": "https://x.com", "token": "t"},
            "llm": {"api_key": "k"},
            "codebase": {"git_history_days": -1},
        })


# ---------------------------------------------------------------------------
# masked()
# ---------------------------------------------------------------------------


def test_masked_hides_youtrack_token(monkeypatch, tmp_path):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = load_settings(tmp_path / "none.yaml")
    d = settings.masked()
    assert d["youtrack"]["token"] == "***"


def test_masked_hides_llm_api_key(monkeypatch, tmp_path):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = load_settings(tmp_path / "none.yaml")
    d = settings.masked()
    assert d["llm"]["api_key"] == "***"


def test_masked_preserves_non_secret_fields(monkeypatch, tmp_path):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = load_settings(tmp_path / "none.yaml")
    d = settings.masked()
    assert d["youtrack"]["url"] == "https://test.youtrack.cloud"
    assert d["llm"]["provider"] == "anthropic"
    assert d["llm"]["model"] == DEFAULT_LLM_MODEL


def test_masked_does_not_modify_original(monkeypatch, tmp_path):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = load_settings(tmp_path / "none.yaml")
    settings.masked()
    assert settings.youtrack.token == "test-token"
    assert settings.llm.api_key == "test-api-key"
