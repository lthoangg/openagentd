"""Tests for app/cli/commands/auth.py — central OAuth dispatcher."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from app.cli.commands.auth import _PROVIDERS, _list_providers, _run_login, main


# ---------------------------------------------------------------------------
# _list_providers
# ---------------------------------------------------------------------------


class TestListProviders:
    def test_prints_available_providers(self, capsys):
        _list_providers()
        out = capsys.readouterr().out
        assert "copilot" in out

    def test_prints_description(self, capsys):
        _list_providers()
        out = capsys.readouterr().out
        # Me check description text present
        assert "GitHub Copilot" in out

    def test_prints_usage_hint(self, capsys):
        _list_providers()
        out = capsys.readouterr().out
        assert "openagentd auth" in out

    def test_all_providers_listed(self, capsys):
        _list_providers()
        out = capsys.readouterr().out
        for name in _PROVIDERS:
            assert name in out


# ---------------------------------------------------------------------------
# _run_login
# ---------------------------------------------------------------------------


class TestRunLogin:
    def test_unknown_provider_prints_error(self, capsys):
        with pytest.raises(SystemExit):
            _run_login("nonexistent_provider")
        out = capsys.readouterr().out
        assert "Unknown provider" in out

    def test_unknown_provider_exits_1(self):
        with pytest.raises(SystemExit) as exc_info:
            _run_login("nonexistent_provider")
        assert exc_info.value.code == 1

    def test_unknown_provider_lists_available(self, capsys):
        with pytest.raises(SystemExit):
            _run_login("bad_provider")
        out = capsys.readouterr().out
        # Me list_providers also called — copilot should appear
        assert "copilot" in out

    def test_known_provider_imports_module(self):
        mock_mod = MagicMock()
        mock_mod.login = MagicMock()
        with patch("importlib.import_module", return_value=mock_mod) as mock_import:
            _run_login("copilot")
        mock_import.assert_called_once_with("app.agent.providers.copilot.oauth")

    def test_known_provider_calls_login(self):
        mock_mod = MagicMock()
        mock_mod.login = MagicMock()
        with patch("importlib.import_module", return_value=mock_mod):
            _run_login("copilot")
        mock_mod.login.assert_called_once()

    def test_run_login_dispatches_correct_module(self):
        """Me verify module path matches _PROVIDERS registry."""
        mock_mod = MagicMock()
        with patch("importlib.import_module", return_value=mock_mod) as mock_import:
            _run_login("copilot")
        expected_module, _ = _PROVIDERS["copilot"]
        mock_import.assert_called_once_with(expected_module)


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_args_calls_list_providers(self, capsys):
        with patch.object(sys, "argv", ["app.auth"]):
            main()
        out = capsys.readouterr().out
        assert "copilot" in out

    def test_list_flag_calls_list_providers(self, capsys):
        with patch.object(sys, "argv", ["app.auth", "--list"]):
            main()
        out = capsys.readouterr().out
        assert "copilot" in out

    def test_provider_arg_calls_run_login(self):
        mock_mod = MagicMock()
        with patch.object(sys, "argv", ["app.auth", "copilot"]):
            with patch("importlib.import_module", return_value=mock_mod):
                main()
        mock_mod.login.assert_called_once()

    def test_unknown_provider_arg_exits(self):
        with patch.object(sys, "argv", ["app.auth", "unknown_xyz"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1

    def test_list_flag_takes_precedence_over_provider(self, capsys):
        """--list flag shows list even when provider arg given."""
        with patch.object(sys, "argv", ["app.auth", "--list", "copilot"]):
            main()
        out = capsys.readouterr().out
        assert "copilot" in out

    def test_providers_dict_has_copilot(self):
        assert "copilot" in _PROVIDERS

    def test_providers_dict_entry_is_tuple(self):
        for name, entry in _PROVIDERS.items():
            assert isinstance(entry, tuple)
            assert len(entry) == 2
