"""Tests for load_summarization_file_config() in app/agent/loader.py.

Tests the YAML frontmatter parsing, caching behavior, and fallback chain.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from app.agent.loader import (
    _SENTINEL,
    load_summarization_file_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_summarization_md(path: Path, frontmatter: dict, body: str = "") -> Path:
    """Write a summarization config .md file with YAML frontmatter."""
    fm = yaml.dump(frontmatter, default_flow_style=False).strip()
    path.write_text(f"---\n{fm}\n---\n\n{body}\n")
    return path


# ---------------------------------------------------------------------------
# Test: Returns None when file does not exist
# ---------------------------------------------------------------------------


def test_returns_none_when_file_does_not_exist(tmp_path):
    """load_summarization_file_config returns None for nonexistent path."""
    nonexistent = tmp_path / "does_not_exist.md"
    result = load_summarization_file_config(path=nonexistent)
    assert result is None


# ---------------------------------------------------------------------------
# Test: Parses all fields correctly
# ---------------------------------------------------------------------------


def test_parses_all_fields_correctly(tmp_path):
    """load_summarization_file_config parses all four fields from YAML."""
    config_file = tmp_path / "summarization.md"
    _write_summarization_md(
        config_file,
        {
            "model": "googlegenai:gemini-2.0-flash",
            "token_threshold": 100000,
            "keep_last_assistants": 3,
            "max_token_length": 10000,
        },
    )

    result = load_summarization_file_config(path=config_file)

    assert result is not None
    assert result.model == "googlegenai:gemini-2.0-flash"
    assert result.token_threshold == 100000
    assert result.keep_last_assistants == 3
    assert result.max_token_length == 10000


# ---------------------------------------------------------------------------
# Test: Partial frontmatter — missing fields are None
# ---------------------------------------------------------------------------


def test_partial_frontmatter_missing_fields_are_none(tmp_path):
    """load_summarization_file_config handles partial YAML — missing fields are None."""
    config_file = tmp_path / "summarization.md"
    _write_summarization_md(
        config_file,
        {
            "model": "openai:gpt-4",
        },
    )

    result = load_summarization_file_config(path=config_file)

    assert result is not None
    assert result.model == "openai:gpt-4"
    assert result.token_threshold is None
    assert result.keep_last_assistants is None
    assert result.max_token_length is None


# ---------------------------------------------------------------------------
# Test: Empty frontmatter (only --- ---)
# ---------------------------------------------------------------------------


def test_empty_frontmatter_all_fields_none(tmp_path):
    """load_summarization_file_config handles empty YAML — all fields None."""
    config_file = tmp_path / "summarization.md"
    # Write with newline after second --- to match regex
    config_file.write_text("---\n\n---\n\nOptional body text.\n")

    result = load_summarization_file_config(path=config_file)

    assert result is not None
    assert result.model is None
    assert result.token_threshold is None
    assert result.keep_last_assistants is None
    assert result.max_token_length is None


# ---------------------------------------------------------------------------
# Test: Raises ValueError on missing frontmatter
# ---------------------------------------------------------------------------


def test_raises_value_error_on_missing_frontmatter(tmp_path):
    """load_summarization_file_config raises ValueError if no --- delimiters."""
    config_file = tmp_path / "summarization.md"
    config_file.write_text("No frontmatter here, just plain text.\n")

    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        load_summarization_file_config(path=config_file)


# ---------------------------------------------------------------------------
# Test: Cache is bypassed when explicit path is given
# ---------------------------------------------------------------------------


def test_cache_bypassed_with_explicit_path(tmp_path):
    """load_summarization_file_config bypasses cache when explicit path is given."""
    config_file = tmp_path / "summarization.md"
    _write_summarization_md(
        config_file,
        {
            "model": "googlegenai:gemini-2.0-flash",
            "token_threshold": 50000,
        },
    )

    # Call twice with same explicit path
    result1 = load_summarization_file_config(path=config_file)
    result2 = load_summarization_file_config(path=config_file)

    # Both should return equal results (not the same object, but equal values)
    assert result1 is not None
    assert result2 is not None
    assert result1.model == result2.model
    assert result1.token_threshold == result2.token_threshold


# ---------------------------------------------------------------------------
# Test: Cache works for None path
# ---------------------------------------------------------------------------


def test_cache_works_for_none_path(tmp_path, monkeypatch):
    """load_summarization_file_config caches result when path=None."""
    # Reset the cache to _SENTINEL before the test
    import app.agent.loader as loader_module

    monkeypatch.setattr(loader_module, "_summarization_file_cfg_cache", _SENTINEL)

    config_file = tmp_path / "summarization.md"
    _write_summarization_md(
        config_file,
        {
            "model": "zai:glm-5-turbo",
            "token_threshold": 75000,
        },
    )

    # Mock the path resolver to point to our test file
    with patch(
        "app.agent.hooks.summarization.summarization_config_path",
        return_value=config_file,
    ):
        # First call with path=None — should load and cache
        result1 = load_summarization_file_config(path=None)
        assert result1 is not None
        assert result1.model == "zai:glm-5-turbo"

        # Second call with path=None — should return cached result
        result2 = load_summarization_file_config(path=None)
        assert result2 is result1  # Same object (cache hit)


# ---------------------------------------------------------------------------
# Test: Cache returns None when file does not exist
# ---------------------------------------------------------------------------


def test_cache_returns_none_when_file_not_found(tmp_path, monkeypatch):
    """load_summarization_file_config caches None when file does not exist."""
    import app.agent.loader as loader_module

    monkeypatch.setattr(loader_module, "_summarization_file_cfg_cache", _SENTINEL)

    nonexistent = tmp_path / "does_not_exist.md"

    with patch(
        "app.agent.hooks.summarization.summarization_config_path",
        return_value=nonexistent,
    ):
        # First call — file does not exist, returns None and caches it
        result1 = load_summarization_file_config(path=None)
        assert result1 is None

        # Second call — should return cached None
        result2 = load_summarization_file_config(path=None)
        assert result2 is None


# ---------------------------------------------------------------------------
# Test: Pydantic validation — invalid field types raise error
# ---------------------------------------------------------------------------


def test_pydantic_validation_invalid_field_types(tmp_path):
    """load_summarization_file_config raises on invalid field types."""
    config_file = tmp_path / "summarization.md"
    # token_threshold should be int, not string
    _write_summarization_md(
        config_file,
        {
            "model": "googlegenai:gemini-2.0-flash",
            "token_threshold": "not_an_int",  # Invalid
        },
    )

    with pytest.raises(Exception):  # Pydantic validation error
        load_summarization_file_config(path=config_file)


# ---------------------------------------------------------------------------
# Test: Whitespace handling in frontmatter
# ---------------------------------------------------------------------------


def test_whitespace_handling_in_frontmatter(tmp_path):
    """load_summarization_file_config handles whitespace in YAML correctly."""
    config_file = tmp_path / "summarization.md"
    # Write with extra whitespace
    config_file.write_text(
        "---\n"
        "model: googlegenai:gemini-2.0-flash\n"
        "token_threshold: 100000\n"
        "---\n"
        "\n"
        "Optional body.\n"
    )

    result = load_summarization_file_config(path=config_file)

    assert result is not None
    assert result.model == "googlegenai:gemini-2.0-flash"
    assert result.token_threshold == 100000


# ---------------------------------------------------------------------------
# Test: CRLF line endings (Windows)
# ---------------------------------------------------------------------------


def test_crlf_line_endings(tmp_path):
    """load_summarization_file_config handles CRLF line endings."""
    config_file = tmp_path / "summarization.md"
    # Write with CRLF line endings
    config_file.write_text(
        "---\r\n"
        "model: googlegenai:gemini-2.0-flash\r\n"
        "token_threshold: 100000\r\n"
        "---\r\n"
        "\r\n"
        "Body.\r\n"
    )

    result = load_summarization_file_config(path=config_file)

    assert result is not None
    assert result.model == "googlegenai:gemini-2.0-flash"
    assert result.token_threshold == 100000


# ---------------------------------------------------------------------------
# Prompt body parsing
# ---------------------------------------------------------------------------


def test_non_empty_body_becomes_prompt(tmp_path):
    """Markdown body after the closing '---' is captured as the prompt."""
    config_file = tmp_path / "summarization.md"
    config_file.write_text(
        "---\ntoken_threshold: 100000\n---\n\nYou are a test summariser. Be concise.\n"
    )

    result = load_summarization_file_config(path=config_file)

    assert result is not None
    assert result.prompt == "You are a test summariser. Be concise."


def test_empty_body_prompt_is_none(tmp_path):
    """Empty/whitespace-only body leaves prompt as None."""
    config_file = tmp_path / "summarization.md"
    config_file.write_text("---\ntoken_threshold: 100000\n---\n\n   \n")

    result = load_summarization_file_config(path=config_file)

    assert result is not None
    assert result.prompt is None


def test_prompt_in_frontmatter_is_ignored(tmp_path):
    """A `prompt:` key in the YAML frontmatter is discarded — body wins."""
    config_file = tmp_path / "summarization.md"
    config_file.write_text(
        "---\n"
        "prompt: should_be_ignored\n"
        "token_threshold: 100000\n"
        "---\n"
        "\n"
        "real prompt from body\n"
    )

    result = load_summarization_file_config(path=config_file)

    assert result is not None
    assert result.prompt == "real prompt from body"
