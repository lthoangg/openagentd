"""``openagentd update`` — self-upgrade via ``uv`` or ``pip``."""

from __future__ import annotations

import argparse
import os
import shutil

from app.cli.ui import _bold, _cyan


def cmd_update(_args: argparse.Namespace) -> None:
    """Update openagentd to the latest version."""
    if shutil.which("uv"):
        print(f"  {_bold('Updating openagentd')} via {_cyan('uv')} ...")
        os.execvp("uv", ["uv", "tool", "upgrade", "openagentd"])
    else:
        print(f"  {_bold('Updating openagentd')} via {_cyan('pip')} ...")
        os.execvp("pip", ["pip", "install", "--upgrade", "openagentd"])
