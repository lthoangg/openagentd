"""``openagentd update`` / ``openagentd upgrade`` — self-upgrade.

Detection order (first match wins):
1. Homebrew  — executable lives under a Cellar or opt path, or ``brew`` lists it.
2. uv tool   — ``uv`` is on PATH and the tool is in uv's tool environment.
3. pipx      — ``pipx`` is on PATH.
4. pip       — fallback.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.cli.ui import _bold, _cyan, _dim


def _is_brew_managed() -> bool:
    """Return True when the running executable is inside a Homebrew prefix."""
    try:
        exe = Path(sys.executable).resolve()
        brew = shutil.which("brew")
        if not brew:
            return False
        # Fast path: path contains Cellar or opt (works for both Intel and Apple Silicon).
        parts = exe.parts
        if "Cellar" in parts or ("Homebrew" in parts and "opt" in parts):
            return True
        # Slow path: ask brew directly (spawns a subprocess but only as a fallback).
        result = subprocess.run(
            [brew, "list", "--formula", "openagentd"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _is_uv_tool_managed() -> bool:
    """Return True when uv is available and openagentd is a uv tool."""
    uv = shutil.which("uv")
    if not uv:
        return False
    try:
        result = subprocess.run(
            [uv, "tool", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "openagentd" in result.stdout
    except Exception:
        return False


def _is_pipx_managed() -> bool:
    """Return True when pipx is available and openagentd is a pipx package."""
    pipx = shutil.which("pipx")
    if not pipx:
        return False
    try:
        result = subprocess.run(
            [pipx, "list", "--short"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "openagentd" in result.stdout
    except Exception:
        return False


def cmd_update(_args: argparse.Namespace) -> None:
    """Update openagentd to the latest version."""
    if _is_brew_managed():
        print(f"  {_bold('Updating openagentd')} via {_cyan('brew')} ...")
        print(f"  {_dim('brew upgrade openagentd')}")
        os.execvp("brew", ["brew", "upgrade", "openagentd"])

    elif _is_uv_tool_managed():
        print(f"  {_bold('Updating openagentd')} via {_cyan('uv tool')} ...")
        print(f"  {_dim('uv tool upgrade openagentd')}")
        os.execvp("uv", ["uv", "tool", "upgrade", "openagentd"])

    elif _is_pipx_managed():
        print(f"  {_bold('Updating openagentd')} via {_cyan('pipx')} ...")
        print(f"  {_dim('pipx upgrade openagentd')}")
        os.execvp("pipx", ["pipx", "upgrade", "openagentd"])

    else:
        print(f"  {_bold('Updating openagentd')} via {_cyan('pip')} ...")
        print(f"  {_dim('pip install --upgrade openagentd')}")
        os.execvp("pip", ["pip", "install", "--upgrade", "openagentd"])
