"""Tests for the DeepSeek provider.

Covers:
- DeepSeekProvider.__init__: inherits OpenAIProvider, sets correct base_url
- DeepSeekProvider class hierarchy
- _make_default_provider_factory: deepseek branch reads DEEPSEEK_API_KEY, passes base_url
- Capabilities: deepseek: prefix fallback → vision=False
- app/core/config.py: DEEPSEEK_API_KEY field present
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agent.providers.capabilities import get_capabilities
from app.agent.providers.deepseek import DeepSeekProvider
from app.agent.providers.deepseek.deepseek import DEEPSEEK_API_BASE
from app.agent.providers.openai import OpenAIProvider


# ============================================================================
# DeepSeekProvider class hierarchy
# ============================================================================


class TestDeepSeekProviderInheritance:
    """DeepSeekProvider must be a subclass of OpenAIProvider."""

    def test_deepseek_provider_is_subclass_of_openai_provider(self):
        assert issubclass(DeepSeekProvider, OpenAIProvider)

    def test_deepseek_api_base_constant(self):
        assert DEEPSEEK_API_BASE == "https://api.deepseek.com/v1"


# ============================================================================
# DeepSeekProvider.__init__
# ============================================================================


class TestDeepSeekProviderInit:
    """DeepSeekProvider constructor wires base_url and delegates to OpenAIProvider."""

    def _make_provider(self, **kwargs) -> DeepSeekProvider:
        """Helper — patch httpx so no real network calls are made."""
        with patch("app.agent.providers.openai.openai.CompletionsHandler"):
            with patch("app.agent.providers.openai.openai.ResponsesHandler"):
                return DeepSeekProvider(
                    api_key="ds-test-key", model="deepseek-v4-flash", **kwargs
                )

    def test_base_url_is_deepseek(self):
        p = self._make_provider()
        assert p.base_url == DEEPSEEK_API_BASE

    def test_model_stored(self):
        p = self._make_provider()
        assert p.model == "deepseek-v4-flash"

    def test_api_key_stored(self):
        p = self._make_provider()
        assert p.api_key == "ds-test-key"

    def test_custom_model(self):
        with patch("app.agent.providers.openai.openai.CompletionsHandler"):
            with patch("app.agent.providers.openai.openai.ResponsesHandler"):
                p = DeepSeekProvider(api_key="ds-test-key", model="deepseek-v4-pro")
        assert p.model == "deepseek-v4-pro"

    def test_empty_api_key_raises(self):
        with pytest.raises(ValueError, match="API key"):
            DeepSeekProvider(api_key="", model="deepseek-v4-flash")

    def test_temperature_forwarded(self):
        p = self._make_provider(temperature=0.5)
        assert p.temperature == 0.5

    def test_top_p_forwarded(self):
        p = self._make_provider(top_p=0.9)
        assert p.top_p == 0.9

    def test_max_tokens_forwarded(self):
        p = self._make_provider(max_tokens=1024)
        assert p.max_tokens == 1024

    def test_model_kwargs_forwarded(self):
        p = self._make_provider(model_kwargs={"extra_param": "value"})
        assert p.model_kwargs.get("extra_param") == "value"

    def test_default_temperature_is_none(self):
        p = self._make_provider()
        assert p.temperature is None

    def test_default_max_tokens_is_none(self):
        p = self._make_provider()
        assert p.max_tokens is None


# ============================================================================
# Provider factory — deepseek branch
# ============================================================================


class TestDeepSeekProviderFactory:
    """_make_default_provider_factory correctly builds DeepSeekProvider for deepseek: models."""

    def test_factory_calls_deepseek_provider_with_correct_api_key(self):
        from app.agent.providers.factory import build_provider

        mock_provider = MagicMock()
        with patch(
            "app.agent.providers.factory.DeepSeekProvider",
            return_value=mock_provider,
        ) as MockDS:
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.DEEPSEEK_API_KEY = MagicMock()
                mock_settings.DEEPSEEK_API_KEY.get_secret_value.return_value = (
                    "ds-secret"
                )
                build_provider("deepseek:deepseek-v4-flash")

            MockDS.assert_called_once()
            call_kwargs = MockDS.call_args.kwargs
            assert call_kwargs.get("api_key") == "ds-secret"
            assert call_kwargs.get("model") == "deepseek-v4-flash"

    def test_factory_reads_deepseek_api_key_from_settings(self):
        from app.agent.providers.factory import build_provider

        with patch(
            "app.agent.providers.factory.DeepSeekProvider",
            return_value=MagicMock(),
        ) as MockDS:
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.DEEPSEEK_API_KEY = MagicMock()
                mock_settings.DEEPSEEK_API_KEY.get_secret_value.return_value = (
                    "ds-from-settings"
                )
                build_provider("deepseek:deepseek-v4-pro")

            assert MockDS.call_args.kwargs.get("api_key") == "ds-from-settings"

    def test_factory_falls_back_to_env_when_settings_key_is_none(self, monkeypatch):
        from app.agent.providers.factory import build_provider

        monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-from-env")
        with patch(
            "app.agent.providers.factory.DeepSeekProvider",
            return_value=MagicMock(),
        ) as MockDS:
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.DEEPSEEK_API_KEY = None
                build_provider("deepseek:deepseek-v4-flash")

            assert MockDS.call_args.kwargs.get("api_key") == "ds-from-env"

    def test_factory_strips_provider_prefix_from_model(self):
        from app.agent.providers.factory import build_provider

        with patch(
            "app.agent.providers.factory.DeepSeekProvider",
            return_value=MagicMock(),
        ) as MockDS:
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.DEEPSEEK_API_KEY = MagicMock()
                mock_settings.DEEPSEEK_API_KEY.get_secret_value.return_value = "key"
                build_provider("deepseek:deepseek-v4-pro")

            assert MockDS.call_args.kwargs.get("model") == "deepseek-v4-pro"

    def test_factory_unsupported_provider_error_mentions_deepseek(self):
        """deepseek is listed in the supported providers error message."""
        from app.agent.providers.factory import build_provider

        with pytest.raises(ValueError, match="deepseek"):
            build_provider("totally_unknown:model")

    def test_factory_raises_when_deepseek_api_key_missing(self, monkeypatch):
        """Factory raises a clear ValueError when DEEPSEEK_API_KEY is not set."""
        from app.agent.providers.factory import build_provider

        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.DEEPSEEK_API_KEY = None
            with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
                build_provider("deepseek:deepseek-v4-flash")


# ============================================================================
# Capabilities — deepseek: prefix and exact models
# ============================================================================


class TestDeepSeekCapabilities:
    """deepseek: prefix resolves to vision=False; exact models override as needed."""

    def test_deepseek_prefix_vision_false(self):
        caps = get_capabilities("deepseek:some-unknown-model")
        assert caps.input.vision is False

    def test_deepseek_v4_flash_vision_false(self):
        caps = get_capabilities("deepseek:deepseek-v4-flash")
        assert caps.input.vision is False

    def test_deepseek_v4_pro_vision_false(self):
        caps = get_capabilities("deepseek:deepseek-v4-pro")
        assert caps.input.vision is False

    def test_deepseek_prefix_document_text_true(self):
        caps = get_capabilities("deepseek:deepseek-v4-flash")
        assert caps.input.document_text is True

    def test_deepseek_prefix_output_text_true(self):
        caps = get_capabilities("deepseek:deepseek-v4-flash")
        assert caps.output.text is True

    def test_deepseek_prefix_output_image_false(self):
        caps = get_capabilities("deepseek:deepseek-v4-flash")
        assert caps.output.image is False

    def test_deepseek_prefix_audio_false(self):
        caps = get_capabilities("deepseek:deepseek-v4-flash")
        assert caps.input.audio is False

    def test_deepseek_prefix_case_insensitive(self):
        caps_lower = get_capabilities("deepseek:deepseek-v4-flash")
        caps_upper = get_capabilities("DEEPSEEK:deepseek-v4-flash")
        assert caps_lower == caps_upper


# ============================================================================
# Settings — DEEPSEEK_API_KEY field
# ============================================================================


class TestDeepSeekSettings:
    """DEEPSEEK_API_KEY is defined in Settings and defaults to None."""

    def test_deepseek_api_key_field_exists(self):
        from app.core.config import Settings

        s = Settings()
        assert hasattr(s, "DEEPSEEK_API_KEY")

    def test_deepseek_api_key_defaults_to_none(self, monkeypatch):
        from app.core.config import Settings

        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        s = Settings()
        assert s.DEEPSEEK_API_KEY is None

    def test_deepseek_api_key_accepts_string_via_env(self, monkeypatch):
        from app.core.config import Settings

        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-value")
        s = Settings()
        assert s.DEEPSEEK_API_KEY is not None
        assert s.DEEPSEEK_API_KEY.get_secret_value() == "deepseek-test-value"
