"""Tests for app/server.py — the uvicorn entry point."""

from __future__ import annotations

from unittest.mock import patch


def test_server_module_creates_app():
    """Importing app.server produces a FastAPI application."""
    import importlib

    import app.server as server_mod

    importlib.reload(server_mod)

    from starlette.applications import Starlette

    assert server_mod.app is not None
    assert isinstance(server_mod.app, Starlette)


def test_server_main_block_calls_uvicorn_run():
    """The __main__ block invokes uvicorn.run with config values."""
    import runpy
    import sys

    # Remove cached module so runpy doesn't warn about re-executing it.
    saved = sys.modules.pop("app.server", None)
    try:
        with patch("uvicorn.run") as mock_run:
            runpy.run_module("app.server", run_name="__main__", alter_sys=False)
    finally:
        if saved is not None:
            sys.modules["app.server"] = saved

    from app.core.config import settings

    mock_run.assert_called_once_with(
        "app.server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
    )
