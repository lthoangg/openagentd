"""First-run detection for ``openagentd``.

When the user types ``openagentd`` and the install hasn't been initialised
yet, the CLI auto-launches ``openagentd init`` before starting the server
— so the headline UX is genuinely one command.

A run is considered uninitialised when **either**:

- The expected ``.env`` file is missing **and** no LLM provider
  credential is present in the environment, **or**
- ``{OPENAGENTD_CONFIG_DIR}/agents/`` does not contain at least one
  ``.md`` file (so the team-manager would load nothing).

Behaviour matrix
----------------

+----------------+---------------+-----------------------------------+
| Initialised?   | Stdin is TTY? | Action                            |
+================+===============+===================================+
| Yes            | —             | Continue normally.                |
+----------------+---------------+-----------------------------------+
| No             | Yes           | Print banner, run ``cmd_init``,   |
|                |               | then continue.                    |
+----------------+---------------+-----------------------------------+
| No             | No            | Print hint, exit 1. Avoids        |
|                |               | silently starting a broken server |
|                |               | from a script / systemd unit.     |
+----------------+---------------+-----------------------------------+
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.cli.paths import _config_dir
from app.cli.ui import _bold, _cyan, _dim, _yellow

#: Env vars whose presence we treat as "user has at least one provider set up."
_PROVIDER_KEYS: tuple[str, ...] = (
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ZAI_API_KEY",
    "NVIDIA_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ROUTER9_API_KEY",
    "CLIPROXY_API_KEY",
    # OAuth-based providers don't expose env vars — initialisation will
    # detect them via the cached oauth.json instead.
    # Vertex AI uses ADC (no API key) plus GOOGLE_CLOUD_PROJECT.
    "GOOGLE_CLOUD_PROJECT",
)


def is_initialised(*, dev: bool) -> bool:
    """Return ``True`` if the install looks ready to start the server."""
    return _has_credentials(dev=dev) and _has_agents(dev=dev)


def ensure_initialised(args: argparse.Namespace) -> None:
    """Run interactive ``cmd_init`` if the install isn't ready.

    Exits the process with code 1 in non-interactive contexts so that
    scripts get a clear error instead of a silently broken server.
    """
    dev: bool = bool(getattr(args, "dev", False))
    if is_initialised(dev=dev):
        return

    print()
    print(f"  {_bold(_cyan('Welcome to OpenAgentd!'))}")
    print(f"  {_dim('No configuration found. Setting up your install now…')}")
    print()

    if not sys.stdin.isatty():
        print(
            f"  {_yellow('!')}  No \033[1m.env\033[0m or agents detected and stdin is not a TTY."
        )
        print(f"     Run {_bold('openagentd init')} interactively first.")
        print()
        sys.exit(1)

    # Lazy import so plain ``--help`` / ``status`` don't pay the cost.
    from app.cli.commands.init import cmd_init

    init_args = argparse.Namespace(dev=dev)
    cmd_init(init_args)


# ── Internals ────────────────────────────────────────────────────────────────


def _has_credentials(*, dev: bool) -> bool:
    """A credential exists if any provider env var is set OR an .env file
    that looks populated lives where settings will load it from.
    """
    if any(os.environ.get(k) for k in _PROVIDER_KEYS):
        return True

    env_file = _env_file(dev=dev)
    if env_file.is_file():
        # Treat any non-comment, non-blank line as evidence the user has
        # configured something — we don't try to validate keys here.
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return True
    return False


def _has_agents(*, dev: bool) -> bool:
    """At least one ``.md`` file must live in ``{OPENAGENTD_CONFIG_DIR}/agents/``."""
    agents_dir = _config_dir(dev) / "agents"
    if not agents_dir.is_dir():
        return False
    return any(agents_dir.glob("*.md"))


def _env_file(*, dev: bool) -> Path:
    """Path to the ``.env`` we expect ``openagentd init`` to have written.

    Mirrors the logic in ``cmd_init``: dev mode writes to the project
    root; production writes inside the XDG config dir.
    """
    return Path(".env") if dev else _config_dir(dev) / ".env"
