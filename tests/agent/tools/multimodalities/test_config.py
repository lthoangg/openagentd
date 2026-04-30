"""Tests for the ``multimodal.yaml`` loader — parse + validation of the
``model: <provider>:<name>`` format.

Backend-specific behaviour is covered in ``test_openai_backend.py``;
these tests only exercise ``get_section``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.tools.multimodalities import _config as mm_config
from app.agent.tools.multimodalities._config import get_section


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setattr("app.core.config.settings.OPENAGENTD_CONFIG_DIR", str(cfg))
    monkeypatch.setattr(mm_config, "_cache", None)
    return cfg


def _write(config_dir: Path, body: str) -> None:
    (config_dir / "multimodal.yaml").write_text(body, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_parses_provider_and_model_from_combined_field(config_dir: Path) -> None:
    _write(config_dir, "image:\n  model: openai:gpt-image-2\n  size: 1024x1024\n")
    cfg = get_section("image")
    assert cfg is not None
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-image-2"
    assert cfg.extras == {"size": "1024x1024"}


def test_parser_is_permissive_about_unregistered_providers(
    config_dir: Path,
) -> None:
    """Parser accepts any ``provider:name`` string — dispatch is the gate.

    Keeps parsing decoupled from the registered-backends list so adding or
    removing a backend only touches ``_IMAGE_BACKENDS`` in ``image.py``.
    """
    _write(config_dir, "image:\n  model: stability:sdxl\n")
    cfg = get_section("image")
    assert cfg is not None
    assert cfg.provider == "stability"
    assert cfg.model == "sdxl"


def test_model_with_colons_in_name_uses_first_colon(config_dir: Path) -> None:
    """``provider:name`` splits on the first ``:`` only — e.g. ``openai:ft:foo:bar``."""
    _write(config_dir, "image:\n  model: openai:ft:my-model:v1\n")
    cfg = get_section("image")
    assert cfg is not None
    assert cfg.provider == "openai"
    assert cfg.model == "ft:my-model:v1"


def test_extras_exclude_model_key(config_dir: Path) -> None:
    _write(
        config_dir,
        "image:\n  model: openai:gpt-image-2\n  size: 1024x1024\n  quality: high\n",
    )
    cfg = get_section("image")
    assert cfg is not None
    assert "model" not in cfg.extras
    assert cfg.extras == {"size": "1024x1024", "quality": "high"}


# ─────────────────────────────────────────────────────────────────────────────
# Failure modes — all return None + log warning
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_file_returns_none(config_dir: Path) -> None:
    # No file written.
    assert get_section("image") is None


def test_missing_section_returns_none(config_dir: Path) -> None:
    _write(config_dir, "audio:\n  model: openai:tts-1\n")
    assert get_section("image") is None


def test_legacy_provider_field_hard_fails(config_dir: Path) -> None:
    """Old ``provider:`` + ``model:`` split shape is rejected outright."""
    _write(config_dir, "image:\n  provider: openai\n  model: gpt-image-2\n")
    assert get_section("image") is None


def test_model_without_colon_returns_none(config_dir: Path) -> None:
    _write(config_dir, "image:\n  model: gpt-image-2\n")
    assert get_section("image") is None


def test_model_empty_provider_returns_none(config_dir: Path) -> None:
    _write(config_dir, "image:\n  model: ':gpt-image-2'\n")
    assert get_section("image") is None


def test_model_empty_name_returns_none(config_dir: Path) -> None:
    _write(config_dir, "image:\n  model: 'openai:'\n")
    assert get_section("image") is None


def test_model_non_string_returns_none(config_dir: Path) -> None:
    _write(config_dir, "image:\n  model: 42\n")
    assert get_section("image") is None


def test_missing_model_key_returns_none(config_dir: Path) -> None:
    _write(config_dir, "image:\n  size: 1024x1024\n")
    assert get_section("image") is None
