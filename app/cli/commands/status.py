"""``openagentd status`` — report whether a background openagentd is running."""

from __future__ import annotations

import argparse

from app.cli.paths import _server_log
from app.cli.pids import _find_pids, _pid_alive
from app.cli.ui import _dim, _green, _yellow


def cmd_status(_args: argparse.Namespace) -> None:
    pids, dev = _find_pids()
    alive = [p for p in pids if _pid_alive(p)]
    if alive:
        print(f"  {_green('running')}  pids: {', '.join(str(p) for p in alive)}")
        print(f"  {_dim('Logs:')} {_server_log(dev)}")
    else:
        print(f"  {_yellow('stopped')}")
