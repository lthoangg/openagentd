"""Tests for app/api/routes/scheduler.py — REST endpoints for scheduled tasks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.core.db as _db_module
from app.api.routes.scheduler import get_scheduler, router
from app.scheduler.scheduler import TaskScheduler
from app.services import team_manager


_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_scheduler():
    """An isolated scheduler bound to the in-memory test DB."""
    return TaskScheduler(db_factory=_db_module.async_session_factory)


@pytest.fixture
def stub_team(monkeypatch):
    """Install a fake team into team_manager so _require_agent passes."""
    fake = MagicMock()
    fake.lead = MagicMock(name="lead")
    fake.lead.name = "lead"
    fake.members = {"worker": MagicMock()}
    monkeypatch.setattr(team_manager, "_team", fake)
    yield fake
    monkeypatch.setattr(team_manager, "_team", None)


@pytest.fixture
async def client(fresh_scheduler):
    app = FastAPI()
    app.include_router(router, prefix="/api/scheduler")
    app.dependency_overrides[get_scheduler] = lambda: fresh_scheduler

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c

    await fresh_scheduler.stop()


def _create_payload(**overrides) -> dict:
    payload = {
        "name": "task1",
        "agent": "lead",
        "schedule_type": "every",
        "every_seconds": 60,
        "prompt": "hello",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# POST /tasks
# ---------------------------------------------------------------------------


class TestCreate:
    async def test_creates_task_201(self, client, stub_team):
        resp = await client.post("/api/scheduler/tasks", json=_create_payload())
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "task1"
        assert body["agent"] == "lead"
        assert body["schedule_type"] == "every"
        assert body["every_seconds"] == 60
        assert body["enabled"] is True
        assert body["status"] == "pending"
        assert body["next_fire_at"] is not None

    async def test_unknown_agent_returns_422(self, client, stub_team):
        resp = await client.post(
            "/api/scheduler/tasks",
            json=_create_payload(agent="nonexistent"),
        )
        assert resp.status_code == 422
        assert "not found in the current team" in resp.json()["detail"]

    async def test_no_team_configured_returns_422(self, client, monkeypatch):
        monkeypatch.setattr(team_manager, "_team", None)
        resp = await client.post("/api/scheduler/tasks", json=_create_payload())
        assert resp.status_code == 422
        assert "No team configured" in resp.json()["detail"]

    async def test_duplicate_name_returns_409(self, client, stub_team):
        first = await client.post(
            "/api/scheduler/tasks", json=_create_payload(name="dup")
        )
        assert first.status_code == 201
        second = await client.post(
            "/api/scheduler/tasks", json=_create_payload(name="dup")
        )
        assert second.status_code == 409
        assert "already exists" in second.json()["detail"]

    async def test_invalid_schedule_returns_422(self, client, stub_team):
        # at without at_datetime
        resp = await client.post(
            "/api/scheduler/tasks",
            json={
                "name": "bad",
                "agent": "lead",
                "schedule_type": "at",
                "prompt": "hi",
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /tasks
# ---------------------------------------------------------------------------


class TestList:
    async def test_empty_list(self, client, stub_team):
        resp = await client.get("/api/scheduler/tasks")
        assert resp.status_code == 200
        assert resp.json() == {"tasks": []}

    async def test_returns_persisted_tasks(self, client, stub_team):
        await client.post("/api/scheduler/tasks", json=_create_payload(name="a"))
        await client.post("/api/scheduler/tasks", json=_create_payload(name="b"))
        resp = await client.get("/api/scheduler/tasks")
        assert resp.status_code == 200
        names = sorted(t["name"] for t in resp.json()["tasks"])
        assert names == ["a", "b"]


# ---------------------------------------------------------------------------
# GET /tasks/{task_id}
# ---------------------------------------------------------------------------


class TestGet:
    async def test_returns_task(self, client, stub_team):
        created = await client.post(
            "/api/scheduler/tasks", json=_create_payload(name="findable")
        )
        task_id = created.json()["id"]

        resp = await client.get(f"/api/scheduler/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "findable"

    async def test_unknown_id_returns_404(self, client):
        resp = await client.get(f"/api/scheduler/tasks/{uuid4()}")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# PUT /tasks/{task_id}
# ---------------------------------------------------------------------------


class TestUpdate:
    async def test_updates_fields(self, client, stub_team):
        created = await client.post(
            "/api/scheduler/tasks", json=_create_payload(name="upd")
        )
        task_id = created.json()["id"]

        resp = await client.put(
            f"/api/scheduler/tasks/{task_id}",
            json={"every_seconds": 30, "prompt": "new prompt"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["every_seconds"] == 30
        assert body["prompt"] == "new prompt"

    async def test_validates_new_agent(self, client, stub_team):
        created = await client.post(
            "/api/scheduler/tasks", json=_create_payload(name="upd2")
        )
        task_id = created.json()["id"]

        resp = await client.put(
            f"/api/scheduler/tasks/{task_id}",
            json={"agent": "ghost"},
        )
        assert resp.status_code == 422

    async def test_unknown_id_returns_404(self, client, stub_team):
        resp = await client.put(
            f"/api/scheduler/tasks/{uuid4()}",
            json={"prompt": "x"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /tasks/{task_id}
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_deletes_task_204(self, client, stub_team, fresh_scheduler):
        created = await client.post(
            "/api/scheduler/tasks", json=_create_payload(name="del")
        )
        task_id = created.json()["id"]

        resp = await client.delete(f"/api/scheduler/tasks/{task_id}")
        assert resp.status_code == 204

        # Confirm gone
        get_resp = await client.get(f"/api/scheduler/tasks/{task_id}")
        assert get_resp.status_code == 404

    async def test_unknown_id_returns_404(self, client):
        resp = await client.delete(f"/api/scheduler/tasks/{uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /tasks/{id}/pause + /resume
# ---------------------------------------------------------------------------


class TestPauseResume:
    async def test_pause_sets_paused(self, client, stub_team):
        created = await client.post(
            "/api/scheduler/tasks", json=_create_payload(name="p")
        )
        task_id = created.json()["id"]
        resp = await client.post(f"/api/scheduler/tasks/{task_id}/pause")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["status"] == "paused"

    async def test_resume_re_enables(self, client, stub_team):
        created = await client.post(
            "/api/scheduler/tasks", json=_create_payload(name="r")
        )
        task_id = created.json()["id"]
        await client.post(f"/api/scheduler/tasks/{task_id}/pause")
        resp = await client.post(f"/api/scheduler/tasks/{task_id}/resume")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["status"] == "pending"

    async def test_pause_unknown_id_404(self, client):
        resp = await client.post(f"/api/scheduler/tasks/{uuid4()}/pause")
        assert resp.status_code == 404

    async def test_resume_unknown_id_404(self, client):
        resp = await client.post(f"/api/scheduler/tasks/{uuid4()}/resume")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /tasks/{id}/trigger
# ---------------------------------------------------------------------------


class TestTrigger:
    async def test_returns_202_and_dispatched_status(
        self, client, stub_team, monkeypatch
    ):
        # Stub _fire_task so the test doesn't actually invoke any team logic.
        async def _noop(task):
            return None

        monkeypatch.setattr(
            "app.scheduler.scheduler.TaskScheduler._fire_task",
            lambda self, task: _noop(task),
        )

        created = await client.post(
            "/api/scheduler/tasks", json=_create_payload(name="trig")
        )
        task_id = created.json()["id"]
        resp = await client.post(f"/api/scheduler/tasks/{task_id}/trigger")
        assert resp.status_code == 202
        assert resp.json() == {"status": "dispatched"}

    async def test_unknown_id_returns_404(self, client):
        resp = await client.post(f"/api/scheduler/tasks/{uuid4()}/trigger")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Schedule type "at" — round-trip
# ---------------------------------------------------------------------------


class TestAtTask:
    async def test_create_at_with_future_datetime(self, client, stub_team):
        target = (datetime.now(_UTC) + timedelta(hours=1)).isoformat()
        resp = await client.post(
            "/api/scheduler/tasks",
            json={
                "name": "at_one",
                "agent": "lead",
                "schedule_type": "at",
                "at_datetime": target,
                "prompt": "hi",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["schedule_type"] == "at"
        assert body["at_datetime"] is not None
        assert body["next_fire_at"] is not None


# ---------------------------------------------------------------------------
# Schedule type "cron" — round-trip
# ---------------------------------------------------------------------------


class TestCronTask:
    async def test_create_with_valid_cron(self, client, stub_team):
        resp = await client.post(
            "/api/scheduler/tasks",
            json={
                "name": "cron_one",
                "agent": "lead",
                "schedule_type": "cron",
                "cron_expression": "0 0 * * *",
                "prompt": "hi",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["schedule_type"] == "cron"
        assert body["cron_expression"] == "0 0 * * *"

    async def test_invalid_cron_rejected_422(self, client, stub_team):
        resp = await client.post(
            "/api/scheduler/tasks",
            json={
                "name": "bad_cron",
                "agent": "lead",
                "schedule_type": "cron",
                "cron_expression": "totally bogus",
                "prompt": "hi",
            },
        )
        assert resp.status_code == 422
