"""XDG-aware directory resolvers and standard log/PID file paths.

Production mode uses XDG base-directory layout under ``$HOME``; development
mode uses a project-local ``.openagentd/`` tree.  Each resolver honours an
``OPENAGENTD_*`` env var override so tests (and power users) can redirect paths.
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_WEB_DIR = _ROOT / "web"


def _state_dir(dev: bool) -> Path:
    """Return the state directory (logs, pid files) for the current mode.

    - production (dev=False) → ~/.local/state/openagentd  (XDG_STATE_HOME)
    - development (dev=True) → .openagentd/state  (project-local)

    Respects an explicit ``OPENAGENTD_STATE_DIR`` env var in both cases.
    """
    if "OPENAGENTD_STATE_DIR" in os.environ:
        return Path(os.environ["OPENAGENTD_STATE_DIR"])
    if dev:
        return Path(".openagentd") / "state"
    return Path.home() / ".local" / "state" / "openagentd"


def _data_dir(dev: bool) -> Path:
    """Return the data directory (DB, workspaces) for the current mode.

    - production → ~/.local/share/openagentd  (XDG_DATA_HOME)
    - development → .openagentd/data  (project-local)
    """
    if "OPENAGENTD_DATA_DIR" in os.environ:
        return Path(os.environ["OPENAGENTD_DATA_DIR"])
    if dev:
        return Path(".openagentd") / "data"
    return Path.home() / ".local" / "share" / "openagentd"


def _config_dir(dev: bool) -> Path:
    """Return the config directory (agents, skills, .env) for the current mode.

    - production → ~/.config/openagentd  (XDG_CONFIG_HOME)
    - development → .openagentd/config  (project-local)
    """
    if "OPENAGENTD_CONFIG_DIR" in os.environ:
        return Path(os.environ["OPENAGENTD_CONFIG_DIR"])
    if dev:
        return Path(".openagentd") / "config"
    return Path.home() / ".config" / "openagentd"


def _pid_file(dev: bool) -> Path:
    return _state_dir(dev) / "openagentd.pid"


def _server_log(dev: bool) -> Path:
    return _state_dir(dev) / "logs" / "app" / "app.log"


def _web_log(dev: bool) -> Path:
    return _state_dir(dev) / "logs" / "web.log"
