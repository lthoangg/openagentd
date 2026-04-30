"""Tests for app/api/routes/health.py — /live + /ready split."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.health import router
from app.core.db import get_session
from app.core.version import VERSION
from app.services import team_manager


def _make_app(*, db_ok: bool = True, team_present: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/health")

    async def fake_session():
        session = MagicMock()

        async def exec_(_q):  # noqa: ANN001
            if not db_ok:
                raise RuntimeError("db down")
            return None

        session.exec = exec_
        yield session

    app.dependency_overrides[get_session] = fake_session

    # Patch team_manager.current_team()
    if team_present:
        team_manager._team = MagicMock()  # type: ignore[attr-defined]
    else:
        team_manager._team = None  # type: ignore[attr-defined]

    return app


class TestLive:
    def test_live_always_returns_200(self):
        # Even with DB down + no team.
        client = TestClient(_make_app(db_ok=False, team_present=False))
        resp = client.get("/api/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "version": VERSION}


class TestReady:
    def test_ready_ok_when_db_and_team_healthy(self):
        client = TestClient(_make_app(db_ok=True, team_present=True))
        resp = client.get("/api/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["checks"]["db"] == "ok"
        assert body["checks"]["team"] == "ok"

    def test_ready_ok_when_db_healthy_but_team_missing(self):
        """Team absent (empty agents dir) is tolerable — degraded but ready."""
        client = TestClient(_make_app(db_ok=True, team_present=False))
        resp = client.get("/api/health/ready")
        # Current logic: team "missing" still reports ready=True.
        assert resp.status_code == 200
        body = resp.json()
        assert body["checks"]["team"] == "missing"


class TestLegacyAliasRemoved:
    def test_bare_health_returns_404(self):
        """The legacy ``GET /api/health`` alias was removed."""
        client = TestClient(_make_app(db_ok=True, team_present=True))
        resp = client.get("/api/health")
        assert resp.status_code == 404
