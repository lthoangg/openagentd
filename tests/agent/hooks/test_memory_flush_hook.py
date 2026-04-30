"""Tests for memory_flush deprecated stub."""

from __future__ import annotations

from unittest.mock import MagicMock


from app.agent.hooks.memory_flush import build_memory_flush_hook


def test_build_memory_flush_hook_always_returns_none():
    """Deprecated factory always returns None regardless of arguments."""
    provider = MagicMock()
    assert build_memory_flush_hook(provider, 0) is None
    assert build_memory_flush_hook(provider, 1) is None
    assert build_memory_flush_hook(provider, 999_999) is None
