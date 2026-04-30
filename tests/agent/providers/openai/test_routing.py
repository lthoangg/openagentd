"""Tests for `_should_use_responses` — Completions vs Responses API routing.

See `app/agent/providers/openai/openai.py:_should_use_responses`.
"""

from __future__ import annotations

from app.agent.providers.openai.openai import _should_use_responses


# ─────────────────────────────────────────────────────────────────────────────
# Test _should_use_responses() routing logic
# ─────────────────────────────────────────────────────────────────────────────


class TestShouldUseResponses:
    """Test the routing logic that determines which API to use."""

    def test_empty_model_kwargs_defaults_to_completions(self):
        """Empty model_kwargs → use Chat Completions (False)."""
        assert _should_use_responses({}) is False

    def test_explicit_responses_api_true(self):
        """responses_api: true → always use Responses API."""
        assert _should_use_responses({"responses_api": True}) is True

    def test_explicit_responses_api_false(self):
        """responses_api: false → always use Chat Completions."""
        assert _should_use_responses({"responses_api": False}) is False

    def test_thinking_level_low_auto_routes_to_responses(self):
        """thinking_level: 'low' → auto-route to Responses API."""
        assert _should_use_responses({"thinking_level": "low"}) is True

    def test_thinking_level_medium_auto_routes_to_responses(self):
        """thinking_level: 'medium' → auto-route to Responses API."""
        assert _should_use_responses({"thinking_level": "medium"}) is True

    def test_thinking_level_high_auto_routes_to_responses(self):
        """thinking_level: 'high' → auto-route to Responses API."""
        assert _should_use_responses({"thinking_level": "high"}) is True

    def test_thinking_level_none_uses_completions(self):
        """thinking_level: 'none' → use Chat Completions."""
        assert _should_use_responses({"thinking_level": "none"}) is False

    def test_thinking_level_off_uses_completions(self):
        """thinking_level: 'off' → use Chat Completions."""
        assert _should_use_responses({"thinking_level": "off"}) is False

    def test_thinking_level_empty_string_uses_completions(self):
        """thinking_level: '' → use Chat Completions."""
        assert _should_use_responses({"thinking_level": ""}) is False

    def test_explicit_responses_api_overrides_thinking_level(self):
        """Explicit responses_api flag takes priority over thinking_level."""
        # responses_api: false wins even with thinking_level: "low"
        assert (
            _should_use_responses({"thinking_level": "low", "responses_api": False})
            is False
        )
        # responses_api: true wins even with thinking_level: "none"
        assert (
            _should_use_responses({"thinking_level": "none", "responses_api": True})
            is True
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test CompletionsHandler
# ─────────────────────────────────────────────────────────────────────────────
