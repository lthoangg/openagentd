"""``openagentd version`` — print the installed package version."""

from __future__ import annotations

import argparse

from app.core.version import VERSION


def cmd_version(_args: argparse.Namespace) -> None:
    print(f"openagentd v{VERSION}")
