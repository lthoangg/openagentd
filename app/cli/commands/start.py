"""``openagentd`` (default) — launch the server and web UI.

Two modes:

- **production** (default): single detached uvicorn process serving the
  bundled web UI from ``app/_web_dist/``; stdout/stderr redirected to the
  server log so the user gets their shell back.
- **development** (``--dev``): uvicorn in the foreground with hot-reload,
  plus a separate ``bun dev`` Vite process for frontend HMR.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys

from app.cli.firstrun import ensure_initialised
from app.cli.paths import _WEB_DIR, _ROOT, _server_log
from app.cli.pids import _clear_pids, _find_pids, _pid_alive, _write_pids
from app.cli.server import _has_bundled_web, _server_cmd
from app.cli.ui import _bold, _dim, _print_banner, _yellow


_DEV_API_PORT = 8000
_PROD_API_PORT = 4082


def _resolve_port(port: int | None, *, dev: bool) -> int:
    """Pick the API port when the user didn't pass ``--port`` explicitly.

    Dev defaults to 8000 to match Vite's ``/api → :8000`` proxy
    (``web/vite.config.ts``) and the ``make dev`` workflow; production
    defaults to 4082 (the bundled single-process mode). An explicit
    ``--port`` always wins.
    """
    if port is not None:
        return port
    return _DEV_API_PORT if dev else _PROD_API_PORT


def cmd_start(args: argparse.Namespace) -> None:
    dev: bool = args.dev
    args.port = _resolve_port(args.port, dev=dev)

    # First-run guard: if .env or agents are missing, run init interactively
    # before going any further. Headline UX is `openagentd` → working server.
    ensure_initialised(args)

    # Check if already running (search both locations)
    existing_pids, _ = _find_pids()
    if existing_pids and any(_pid_alive(p) for p in existing_pids):
        print(f"  {_yellow('already running')}  (run {_bold('openagentd stop')} first)")
        return

    srv_log = _server_log(dev)

    if dev:
        # ── Development: uvicorn + Vite dev server ────────────────────────
        _print_banner(host=args.host, port=args.port, web_port=args.web_port, dev=True)

        env = {**os.environ, "APP_ENV": "development", "LOG_LEVEL": "DEBUG"}

        server = subprocess.Popen(
            _server_cmd(host=args.host, port=args.port, dev=True),
            cwd=_ROOT,
            env=env,
        )
        # Launch Vite dev server for hot-reload (requires bun + source tree)
        web: subprocess.Popen[bytes] | None = None
        if _WEB_DIR.is_dir():
            web = subprocess.Popen(
                ["bun", "dev", "--host", args.host, "--port", str(args.web_port)],
                cwd=_WEB_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _write_pids([server.pid, web.pid], dev)
        else:
            _write_pids([server.pid], dev)

        procs = [p for p in (server, web) if p is not None]

        def _sig(signum: int, frame: object) -> None:
            for p in procs:
                try:
                    p.terminate()
                except OSError:
                    pass
            _clear_pids(dev)
            sys.exit(0)

        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)
        server.wait()
        for p in procs:
            if p is not server:
                p.terminate()
        _clear_pids(dev)

    else:
        # ── Production: single uvicorn process (web UI bundled) ───────────
        # FastAPI serves the pre-built web/dist/ assets directly.
        # No bun, no Vite, no separate web process needed.
        if not _has_bundled_web():
            print(
                f"  {_yellow('warning:')} No bundled web UI found. "
                f"API will work but no web UI will be served."
            )
            print(f"  {_dim('Build it:')}  make build-web")
            print()

        _print_banner(host=args.host, port=args.port, web_port=None, dev=False)

        srv_log.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "APP_ENV": "production"}

        with open(srv_log, "a") as srv_f:
            server = subprocess.Popen(
                _server_cmd(host=args.host, port=args.port, dev=False),
                cwd=_ROOT,
                env=env,
                stdout=srv_f,
                stderr=srv_f,
                start_new_session=True,
            )

        _write_pids([server.pid], dev)
        print(f"  {_dim('Logs:')}  {srv_log}")
        print(f"  {_dim('Stop:')}  {_bold('openagentd stop')}")
        print()
