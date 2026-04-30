"""PID file helpers: write/read/find running openagentd processes.

Production and development modes use distinct PID files (``_pid_file(dev)``),
so both can coexist on the same machine.  ``_find_pids`` probes production
first and falls back to dev — matching the order a user typically runs.
"""

from __future__ import annotations

import os

from app.cli.paths import _pid_file


def _write_pids(pids: list[int], dev: bool) -> None:
    pid_file = _pid_file(dev)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text("\n".join(str(p) for p in pids))


def _read_pids(dev: bool) -> list[int]:
    pid_file = _pid_file(dev)
    if not pid_file.exists():
        return []
    try:
        return [int(line) for line in pid_file.read_text().splitlines() if line.strip()]
    except ValueError:
        return []


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _find_pids() -> tuple[list[int], bool]:
    """Find running PIDs checking prod location first, then dev."""
    for dev in (False, True):
        pids = _read_pids(dev)
        if pids and any(_pid_alive(p) for p in pids):
            return pids, dev
    return [], False


def _clear_pids(dev: bool) -> None:
    _pid_file(dev).unlink(missing_ok=True)
