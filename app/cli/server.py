"""Helpers for launching the uvicorn server subprocess and detecting assets."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from app.cli.paths import _ROOT


def _check_dir(path: Path, label: str) -> None:
    if not path.is_dir():
        print(f"error: {label} directory not found: {path}", file=sys.stderr)
        sys.exit(1)


def _resolve_uvicorn() -> list[str]:
    """Pick the right uvicorn invocation for the current install.

    1. Sibling of ``sys.executable`` — works for both ``uv tool install``
       wheels (``~/.local/share/uv/tools/openagentd/bin/uvicorn``) and
       plain venvs (``.venv/bin/uvicorn``). This is the common case for
       end users.
    2. ``shutil.which("uvicorn")`` — covers source-checkout dev where
       the user activated their venv themselves.
    3. ``[sys.executable, "-m", "uvicorn"]`` — last-resort fallback so
       we never crash with FileNotFoundError, even on weirdly-shimmed
       installs.

    Note: we deliberately do *not* use ``uv run uvicorn``. ``uv run``
    adds a wrapper process between the daemon parent and the actual
    server, breaking PID-based stop logic and signal propagation.
    """
    sibling = Path(sys.executable).with_name("uvicorn")
    if sibling.is_file():
        return [str(sibling)]
    found = shutil.which("uvicorn")
    if found:
        return [found]
    return [sys.executable, "-m", "uvicorn"]


def _server_cmd(*, host: str, port: int, dev: bool) -> list[str]:
    cmd = [
        *_resolve_uvicorn(),
        "app.server:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if dev:
        # Watch ``app/`` only.  Coupling reloads to the on-disk config tree
        # (agent .md files, skill SKILL.md files, mcp.json, multimodal.yaml)
        # caused noisy restarts whenever the agent itself wrote there, so
        # those edits now require a manual restart in dev — same as prod.
        cmd += ["--reload", "--reload-dir", "app"]
    return cmd


def _has_bundled_web() -> bool:
    """Check if the pre-built web UI is available (in package or web/dist/)."""
    # Inside installed package
    pkg_dist = Path(__file__).resolve().parent.parent / "_web_dist" / "index.html"
    if pkg_dist.is_file():
        return True
    # Dev build
    dev_dist = _ROOT / "web" / "dist" / "index.html"
    return dev_dist.is_file()
