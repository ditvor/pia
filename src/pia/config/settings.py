"""Pydantic settings model and loader.

Loading priority (highest wins):
  1. Environment variables (explicit list in _apply_env_vars)
  2. YAML config file at ~/.pia/config.yaml  (or custom path)
  3. Built-in defaults from defaults.py

YAML values may reference environment variables using ``${VARNAME}``
syntax — these are interpolated before the rest of the merge.

Usage::

    from pia.config import load_settings

    settings = load_settings()           # uses ~/.pia/config.yaml + env
    settings = load_settings("/tmp/t.yaml")  # explicit path
"""

from __future__ import annotations

import copy
import logging
import os
import pathlib
import re
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from pia.config.defaults import (
    DEFAULT_AGENT_NAME,
    DEFAULT_AGENT_VERSION,
    DEFAULT_AUTH_METHOD,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DATABASE_PATH,
    DEFAULT_EXCLUDE_PATTERNS,
    DEFAULT_GIT_HISTORY_DAYS,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_SYNC_INTERVAL,
    DEFAULT_YOUTRACK_PROJECTS,
)

logger = logging.getLogger(__name__)

# Matches ${VARNAME} references inside YAML string values.
_ENV_REF_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


# ---------------------------------------------------------------------------
# Nested settings models
# ---------------------------------------------------------------------------


class YouTrackSettings(BaseModel):
    """Connection settings for a YouTrack instance."""

    url: str
    token: str
    projects: list[str] = Field(default_factory=lambda: list(DEFAULT_YOUTRACK_PROJECTS))
    sync_interval: int = DEFAULT_SYNC_INTERVAL

    @field_validator("url")
    @classmethod
    def normalise_url(cls, v: str) -> str:
        """Strip trailing slash so callers can safely append paths."""
        return v.rstrip("/")


class LLMSettings(BaseModel):
    """LLM provider and model configuration."""

    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    api_key: str
    max_tokens: int = DEFAULT_LLM_MAX_TOKENS
    temperature: float = DEFAULT_LLM_TEMPERATURE

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"anthropic", "openai"}
        if v not in allowed:
            raise ValueError(f"LLM provider must be one of {allowed}, got {v!r}")
        return v

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"temperature must be between 0.0 and 1.0, got {v}")
        return v


class CodebaseSettings(BaseModel):
    """Settings for the local codebase scanner."""

    # None means "auto-detect from IDE context at runtime".
    root: Optional[str] = None
    exclude_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_EXCLUDE_PATTERNS)
    )
    git_history_days: int = DEFAULT_GIT_HISTORY_DAYS

    @field_validator("git_history_days")
    @classmethod
    def validate_days(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"git_history_days must be non-negative, got {v}")
        return v


class DatabaseSettings(BaseModel):
    """SQLite database location."""

    path: str = DEFAULT_DATABASE_PATH

    @model_validator(mode="after")
    def expand_home(self) -> DatabaseSettings:
        """Expand ``~`` to the user's home directory (including on defaults)."""
        self.path = str(pathlib.Path(self.path).expanduser())
        return self

    @property
    def resolved(self) -> pathlib.Path:
        """Return the database path as a resolved ``Path``."""
        return pathlib.Path(self.path).resolve()


class AgentSettings(BaseModel):
    """ACP agent metadata."""

    name: str = DEFAULT_AGENT_NAME
    version: str = DEFAULT_AGENT_VERSION
    auth_method: str = DEFAULT_AUTH_METHOD


# ---------------------------------------------------------------------------
# Root settings model
# ---------------------------------------------------------------------------


class Settings(BaseModel):
    """Root configuration object for PIA.

    Construct via ``load_settings()`` rather than directly.
    """

    youtrack: YouTrackSettings
    llm: LLMSettings
    codebase: CodebaseSettings = Field(default_factory=CodebaseSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)

    def masked(self) -> dict[str, Any]:
        """Return a dict with secret values replaced by ``'***'``.

        Safe to print or log — use this for ``pia config`` output.
        """
        d = self.model_dump()
        if d.get("youtrack", {}).get("token"):
            d["youtrack"]["token"] = "***"
        if d.get("llm", {}).get("api_key"):
            d["llm"]["api_key"] = "***"
        return d


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*, returning a new dict.

    Nested dicts are merged rather than replaced; all other values from
    *override* take precedence over *base*.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _interpolate_env_refs(value: Any) -> Any:
    """Recursively replace ``${VARNAME}`` strings with environment values.

    If the referenced variable is not set, the placeholder is replaced
    with an empty string so that Pydantic validation can report the
    missing field clearly.
    """
    if isinstance(value, str):
        return _ENV_REF_RE.sub(
            lambda m: os.environ.get(m.group(1), ""),
            value,
        )
    if isinstance(value, dict):
        return {k: _interpolate_env_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env_refs(v) for v in value]
    return value


def _apply_env_vars(data: dict[str, Any]) -> dict[str, Any]:
    """Overlay explicit environment variables onto *data*.

    Env vars listed in the spec section 18 are handled here.  Each var
    is only applied when it is actually set — an unset var never clears
    a value that was already present in the YAML or defaults.

    Args:
        data: Merged dict from defaults + YAML (will not be mutated).

    Returns:
        New dict with env var values applied on top.
    """
    data = copy.deepcopy(data)

    # ---- YouTrack --------------------------------------------------------
    yt: dict[str, Any] = data.setdefault("youtrack", {})
    if v := os.environ.get("YOUTRACK_URL"):
        yt["url"] = v
    if v := os.environ.get("YOUTRACK_TOKEN"):
        yt["token"] = v
    if v := os.environ.get("YOUTRACK_SYNC_INTERVAL"):
        yt["sync_interval"] = int(v)
    if v := os.environ.get("YOUTRACK_PROJECTS"):
        yt["projects"] = [p.strip() for p in v.split(",") if p.strip()]

    # ---- LLM -------------------------------------------------------------
    llm: dict[str, Any] = data.setdefault("llm", {})
    if v := os.environ.get("LLM_PROVIDER"):
        llm["provider"] = v
    if v := os.environ.get("LLM_MODEL"):
        llm["model"] = v
    if v := os.environ.get("LLM_MAX_TOKENS"):
        llm["max_tokens"] = int(v)
    if v := os.environ.get("LLM_TEMPERATURE"):
        llm["temperature"] = float(v)

    # API key: try generic override first, then provider-specific.
    # Determine provider from data (which may have been updated above).
    provider = llm.get("provider", DEFAULT_LLM_PROVIDER)
    provider_key_env = (
        "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
    )
    if v := os.environ.get("LLM_API_KEY"):
        llm["api_key"] = v
    elif v := os.environ.get(provider_key_env):
        llm["api_key"] = v

    # ---- Codebase --------------------------------------------------------
    cb: dict[str, Any] = data.setdefault("codebase", {})
    if v := os.environ.get("CODEBASE_ROOT"):
        cb["root"] = v
    if v := os.environ.get("CODEBASE_GIT_HISTORY_DAYS"):
        cb["git_history_days"] = int(v)

    # ---- Database --------------------------------------------------------
    db: dict[str, Any] = data.setdefault("database", {})
    if v := os.environ.get("PIA_DATABASE_PATH"):
        db["path"] = v

    return data


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------


def load_settings(
    config_path: str | pathlib.Path | None = None,
) -> Settings:
    """Load and validate PIA settings.

    Resolution order (highest priority first):

    1. Environment variables (``YOUTRACK_URL``, ``YOUTRACK_TOKEN``,
       ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``, etc.)
    2. YAML config file (default: ``~/.pia/config.yaml``)
    3. Built-in defaults

    Args:
        config_path: Path to a YAML config file.  ``None`` (default) uses
            ``~/.pia/config.yaml``.  A non-existent path is silently ignored.

    Returns:
        A validated :class:`Settings` instance.

    Raises:
        pydantic.ValidationError: If required fields (``youtrack.url``,
            ``youtrack.token``, ``llm.api_key``) are missing after applying
            all sources.
        yaml.YAMLError: If the config file exists but contains invalid YAML.
    """
    resolved_path = pathlib.Path(
        config_path if config_path is not None else DEFAULT_CONFIG_PATH
    ).expanduser()

    # 1. Load YAML (if present) and interpolate ${VAR} references.
    yaml_data: dict[str, Any] = {}
    if resolved_path.is_file():
        logger.debug("Loading config from %s", resolved_path)
        raw = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            yaml_data = _interpolate_env_refs(raw)
        else:
            logger.warning("Config file %s is empty or not a mapping", resolved_path)
    else:
        logger.debug("Config file %s not found; using env vars and defaults", resolved_path)

    # 2. Overlay env vars (highest priority).
    merged = _apply_env_vars(yaml_data)

    # 3. Validate through Pydantic.
    return Settings.model_validate(merged)
