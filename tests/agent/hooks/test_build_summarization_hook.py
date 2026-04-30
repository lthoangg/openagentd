"""Tests for build_summarization_hook() in app/agent/hooks/summarization.py.

Tests the three-level fallback chain for non-prompt fields:
  1. Per-agent SummarizationConfig
  2. Global SummarizationFileConfig from {CONFIG_DIR}/summarization.md
  3. Module-level DEFAULT_* constants in app.agent.hooks.summarization

The prompt has a single source: the body of {CONFIG_DIR}/summarization.md.
If that file is missing or has an empty body while summarization is enabled,
build_summarization_hook logs a warning and returns ``None`` (mirroring
``build_title_generation_hook``) — the agent runs without the hook rather
than crashing the user's turn mid-flight.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agent.hooks.summarization import (
    DEFAULT_KEEP_LAST_ASSISTANTS,
    DEFAULT_MAX_TOKEN_LENGTH,
    DEFAULT_PROMPT_TOKEN_THRESHOLD,
    SummarizationHook,
    build_summarization_hook,
)
from app.agent.schemas.agent import SummarizationConfig, SummarizationFileConfig

_TEST_PROMPT = "You are a test summariser."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_provider():
    """Return a mock LLMProviderBase."""
    provider = MagicMock()
    provider.stream = MagicMock()
    return provider


def _file_cfg(**overrides) -> SummarizationFileConfig:
    """Build a SummarizationFileConfig with a test prompt baked in."""
    overrides.setdefault("prompt", _TEST_PROMPT)
    return SummarizationFileConfig(**overrides)


# ---------------------------------------------------------------------------
# Disabled / threshold paths → returns None (no prompt required)
# ---------------------------------------------------------------------------


def test_cfg_enabled_false_returns_none(mock_provider):
    """build_summarization_hook returns None when cfg.enabled=False."""
    cfg = SummarizationConfig(enabled=False)
    result = build_summarization_hook(mock_provider, cfg)
    assert result is None


def test_threshold_zero_returns_none(mock_provider):
    """build_summarization_hook returns None when threshold <= 0."""
    cfg = SummarizationConfig(enabled=True, token_threshold=0)
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = None
        result = build_summarization_hook(mock_provider, cfg)
    assert result is None


def test_threshold_negative_returns_none(mock_provider):
    """build_summarization_hook returns None when threshold < 0."""
    cfg = SummarizationConfig(enabled=True, token_threshold=-1)
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = None
        result = build_summarization_hook(mock_provider, cfg)
    assert result is None


# ---------------------------------------------------------------------------
# Prompt required — missing file or empty body degrades gracefully (warn + None)
# ---------------------------------------------------------------------------


def test_missing_file_config_returns_none(mock_provider):
    """No summarization.md in CONFIG_DIR → return None and log a warning.

    Mirrors ``build_title_generation_hook``'s contract so a missing or
    deleted config file degrades to "no summarization, agent still
    responds" instead of crashing the user's turn mid-flight.
    """
    cfg = SummarizationConfig(enabled=True, token_threshold=50000)
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = None
        result = build_summarization_hook(mock_provider, cfg)
    assert result is None


def test_empty_prompt_body_returns_none(mock_provider):
    """File exists but body is empty → return None (don't crash the turn)."""
    cfg = SummarizationConfig(enabled=True, token_threshold=50000)
    file_cfg = SummarizationFileConfig(token_threshold=50000, prompt=None)
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        result = build_summarization_hook(mock_provider, cfg)
    assert result is None


# ---------------------------------------------------------------------------
# Fallback chain — non-prompt fields
# ---------------------------------------------------------------------------


def test_all_none_cfg_uses_file_cfg_values(mock_provider):
    """build_summarization_hook uses file_cfg when cfg is None."""
    file_cfg = _file_cfg(
        model="googlegenai:gemini-2.0-flash",
        token_threshold=50000,
        keep_last_assistants=2,
        max_token_length=5000,
    )
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        with patch(
            "app.agent.hooks.summarization.build_provider"
        ) as mock_build_provider:
            mock_build_provider.return_value = MagicMock()
            result = build_summarization_hook(mock_provider, None)

    assert result is not None
    assert isinstance(result, SummarizationHook)
    assert result._prompt_token_threshold == 50000
    assert result._keep_last_assistants == 2
    assert result._max_token_length == 5000
    assert result._summary_prompt == _TEST_PROMPT


def test_per_agent_cfg_overrides_file_cfg(mock_provider):
    """build_summarization_hook uses agent cfg over file_cfg for each field."""
    cfg = SummarizationConfig(
        enabled=True,
        token_threshold=80000,
        keep_last_assistants=5,
        max_token_length=8000,
    )
    file_cfg = _file_cfg(
        token_threshold=50000,
        keep_last_assistants=2,
        max_token_length=5000,
    )
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        result = build_summarization_hook(mock_provider, cfg)

    assert result is not None
    assert result._prompt_token_threshold == 80000
    assert result._keep_last_assistants == 5
    assert result._max_token_length == 8000


def test_file_cfg_overrides_env_defaults(mock_provider):
    """build_summarization_hook uses file_cfg over settings defaults."""
    file_cfg = _file_cfg(
        token_threshold=60000,
        keep_last_assistants=4,
        max_token_length=7000,
    )
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        result = build_summarization_hook(mock_provider, None)

    assert result is not None
    assert result._prompt_token_threshold == 60000
    assert result._keep_last_assistants == 4
    assert result._max_token_length == 7000


def test_model_from_file_cfg_when_agent_cfg_no_model(mock_provider):
    """build_summarization_hook uses file_cfg model when agent cfg has no model."""
    cfg = SummarizationConfig(enabled=True, token_threshold=50000)
    file_cfg = _file_cfg(
        model="googlegenai:gemini-2.0-flash",
        token_threshold=50000,
    )
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        with patch(
            "app.agent.hooks.summarization.build_provider"
        ) as mock_build_provider:
            mock_new_provider = MagicMock()
            mock_build_provider.return_value = mock_new_provider
            result = build_summarization_hook(mock_provider, cfg)

    assert result is not None
    mock_build_provider.assert_called_once_with("googlegenai:gemini-2.0-flash")
    assert result._llm_provider is mock_new_provider


def test_per_agent_model_overrides_file_cfg_model(mock_provider):
    """build_summarization_hook uses agent model over file_cfg model."""
    cfg = SummarizationConfig(
        enabled=True,
        token_threshold=50000,
        model="openai:gpt-4",
    )
    file_cfg = _file_cfg(
        model="googlegenai:gemini-2.0-flash",
        token_threshold=50000,
    )
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        with patch(
            "app.agent.hooks.summarization.build_provider"
        ) as mock_build_provider:
            mock_new_provider = MagicMock()
            mock_build_provider.return_value = mock_new_provider
            result = build_summarization_hook(mock_provider, cfg)

    assert result is not None
    mock_build_provider.assert_called_once_with("openai:gpt-4")
    assert result._llm_provider is mock_new_provider


def test_no_model_specified_uses_default_provider(mock_provider):
    """build_summarization_hook uses default_provider when no model is specified."""
    cfg = SummarizationConfig(enabled=True, token_threshold=50000)
    file_cfg = _file_cfg(token_threshold=50000)
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        result = build_summarization_hook(mock_provider, cfg)

    assert result is not None
    assert result._llm_provider is mock_provider


def test_partial_cfg_overrides_only_some_fields(mock_provider):
    """build_summarization_hook handles partial cfg overrides correctly."""
    cfg = SummarizationConfig(enabled=True, token_threshold=70000)
    file_cfg = _file_cfg(
        token_threshold=50000,
        keep_last_assistants=2,
        max_token_length=5000,
    )
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        result = build_summarization_hook(mock_provider, cfg)

    assert result is not None
    assert result._prompt_token_threshold == 70000  # from cfg
    assert result._keep_last_assistants == 2  # from file_cfg
    assert result._max_token_length == 5000  # from file_cfg


def test_partial_file_cfg_overrides_only_some_fields(mock_provider):
    """build_summarization_hook handles partial file_cfg overrides correctly."""
    file_cfg = _file_cfg(token_threshold=60000)
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        result = build_summarization_hook(mock_provider, None)

    assert result is not None
    assert result._prompt_token_threshold == 60000
    assert result._keep_last_assistants == DEFAULT_KEEP_LAST_ASSISTANTS
    assert result._max_token_length == DEFAULT_MAX_TOKEN_LENGTH


def test_module_defaults_are_final_fallback(mock_provider):
    """build_summarization_hook uses module-level defaults as final fallback."""
    cfg = SummarizationConfig(enabled=True)  # all None
    file_cfg = _file_cfg()  # only prompt set
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        result = build_summarization_hook(mock_provider, cfg)

    assert result is not None
    assert result._prompt_token_threshold == DEFAULT_PROMPT_TOKEN_THRESHOLD
    assert result._keep_last_assistants == DEFAULT_KEEP_LAST_ASSISTANTS
    assert result._max_token_length == DEFAULT_MAX_TOKEN_LENGTH


def test_returns_summarization_hook_instance(mock_provider):
    """build_summarization_hook returns a SummarizationHook instance."""
    cfg = SummarizationConfig(enabled=True, token_threshold=50000)
    file_cfg = _file_cfg(token_threshold=50000)
    with patch("app.agent.loader.load_summarization_file_config") as mock_load:
        mock_load.return_value = file_cfg
        result = build_summarization_hook(mock_provider, cfg)

    assert isinstance(result, SummarizationHook)
