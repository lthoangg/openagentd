"""Tests for ``app.cli.firstrun``.

Covers the three branches that matter for onboarding correctness:

- Initialised install → ``ensure_initialised`` is a no-op.
- Uninitialised install + non-TTY stdin → exits 1 (script-friendly).
- Uninitialised install + TTY stdin → delegates to ``cmd_init``.

Patch targets follow the same convention as ``test_cli.py``: patch the
**submodule that imported the name**, not the source module.
``firstrun.py`` does ``from app.cli.paths import _config_dir`` so the
patch target is ``app.cli.firstrun._config_dir``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pytest

from app.cli import firstrun


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """Empty config dir that ``firstrun`` will probe for ``agents/``."""
    return tmp_path


def _ns(**kw: object) -> argparse.Namespace:
    return argparse.Namespace(**{"dev": False, **kw})


# ── is_initialised ───────────────────────────────────────────────────────────


def test_is_initialised_true_when_env_var_and_agents_present(
    tmp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Env-var credential plus at least one agent .md → ready to start."""
    (tmp_config / "agents").mkdir()
    (tmp_config / "agents" / "openagentd.md").write_text("---\nname: openagentd\n---\n")

    # Clear any provider keys the host may have set, then set exactly one.
    for key in firstrun._PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with patch("app.cli.firstrun._config_dir", return_value=tmp_config):
        assert firstrun.is_initialised(dev=False) is True


def test_is_initialised_false_when_no_credentials_and_no_env_file(
    tmp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Agents alone aren't enough — we still need a credential somewhere."""
    (tmp_config / "agents").mkdir()
    (tmp_config / "agents" / "openagentd.md").write_text("---\n---\n")

    for key in firstrun._PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch("app.cli.firstrun._config_dir", return_value=tmp_config):
        assert firstrun.is_initialised(dev=False) is False


def test_is_initialised_false_when_credentials_but_no_agents(
    tmp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty agents dir means the team-manager would load nothing."""
    (tmp_config / "agents").mkdir()  # exists but empty

    for key in firstrun._PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "abc")

    with patch("app.cli.firstrun._config_dir", return_value=tmp_config):
        assert firstrun.is_initialised(dev=False) is False


def test_env_file_with_only_comments_does_not_count_as_credential(
    tmp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scaffolded but unedited ``.env`` shouldn't fool the check."""
    (tmp_config / "agents").mkdir()
    (tmp_config / "agents" / "openagentd.md").write_text("---\n---\n")
    (tmp_config / ".env").write_text("# Just a comment\n\n  # another\n")

    for key in firstrun._PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch("app.cli.firstrun._config_dir", return_value=tmp_config):
        assert firstrun.is_initialised(dev=False) is False


def test_env_file_with_real_value_counts_as_credential(
    tmp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_config / "agents").mkdir()
    (tmp_config / "agents" / "openagentd.md").write_text("---\n---\n")
    (tmp_config / ".env").write_text("# header\nOPENAI_API_KEY=sk-real\n")

    for key in firstrun._PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch("app.cli.firstrun._config_dir", return_value=tmp_config):
        assert firstrun.is_initialised(dev=False) is True


# ── ensure_initialised ───────────────────────────────────────────────────────


def test_ensure_initialised_no_op_when_ready(
    tmp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_config / "agents").mkdir()
    (tmp_config / "agents" / "openagentd.md").write_text("---\n---\n")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with patch("app.cli.firstrun._config_dir", return_value=tmp_config):
        # Should NOT call cmd_init and should NOT exit.
        with patch("app.cli.commands.init.cmd_init") as mock_init:
            firstrun.ensure_initialised(_ns(dev=False))
            mock_init.assert_not_called()


def test_ensure_initialised_exits_when_not_a_tty(
    tmp_config: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No config + no TTY → don't silently start a broken server."""
    for key in firstrun._PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)

    with (
        patch("app.cli.firstrun._config_dir", return_value=tmp_config),
        patch("app.cli.firstrun.sys.stdin.isatty", return_value=False),
        pytest.raises(SystemExit) as exc,
    ):
        firstrun.ensure_initialised(_ns(dev=False))

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "openagentd init" in out


def test_ensure_initialised_runs_init_when_tty(
    tmp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No config + TTY → call cmd_init with the right args."""
    for key in firstrun._PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)

    with (
        patch("app.cli.firstrun._config_dir", return_value=tmp_config),
        patch("app.cli.firstrun.sys.stdin.isatty", return_value=True),
        patch("app.cli.commands.init.cmd_init") as mock_init,
    ):
        firstrun.ensure_initialised(_ns(dev=True))

    mock_init.assert_called_once()
    init_ns = mock_init.call_args.args[0]
    assert init_ns.dev is True
