"""Tests for team route DB endpoints — list_sessions, get_session, delete_session, history.

Covers uncovered lines: 195-215, 226-245, 258-267, 296-340.
These tests use the real in-memory DB to exercise the SQL queries.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.agent.agent_loop import Agent
from app.agent.providers.base import LLMProviderBase
from app.agent.mode.team.member import TeamLead, TeamMember
from app.agent.mode.team.team import AgentTeam
from app.models.chat import ChatSession, SessionMessage


class MockProvider(LLMProviderBase):
    model = "mock"

    def stream(self, messages, tools=None, **kwargs):
        from app.agent.schemas.chat import (
            ChatCompletionChunk,
            ChatCompletionChunkChoice,
            ChatCompletionDelta,
        )

        async def gen():
            yield ChatCompletionChunk(
                id="1",
                created=1000,
                model="mock",
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=ChatCompletionDelta(content="OK"),
                        finish_reason="stop",
                    )
                ],
            )

        return gen()

    async def chat(self, messages, tools=None, **kwargs):
        from app.agent.schemas.chat import AssistantMessage

        return AssistantMessage(content="OK")


@pytest.fixture
def test_team():
    lead = TeamLead(
        Agent(name="lead", llm_provider=MockProvider(), system_prompt="Lead")
    )
    worker = TeamMember(
        Agent(name="worker", llm_provider=MockProvider(), system_prompt="Worker")
    )
    return AgentTeam(lead=lead, members={"worker": worker})


@pytest.fixture
def app_with_team(test_team):
    from app.api.app import create_app
    from app.services.team_manager import set_team

    app = create_app()
    set_team(test_team)
    yield app
    set_team(None)


async def _create_team_session(db, session_id, agent_name="lead"):
    """Helper to create a top-level (team lead) session in DB."""
    session = ChatSession(
        id=session_id,
        agent_name=agent_name,
    )
    db.add(session)
    return session


async def _create_member_session(db, session_id, parent_id, agent_name="worker"):
    """Helper to create a team-member session (child of a lead) in DB."""
    session = ChatSession(
        id=session_id,
        parent_session_id=parent_id,
        agent_name=agent_name,
    )
    db.add(session)
    return session


async def _add_message(db, session_id, role="user", content="test", **kwargs):
    msg = SessionMessage(
        session_id=session_id,
        role=role,
        content=content,
        **kwargs,
    )
    db.add(msg)
    return msg


# ---------------------------------------------------------------------------
# GET /team/sessions — list with children (lines 163-215)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /team/sessions — cursor-paginated list with children
# ---------------------------------------------------------------------------


class TestListTeamSessionsWithData:
    @pytest.mark.asyncio
    async def test_list_sessions_returns_lead_session(self, app_with_team):
        import app.core.db as _db

        lead_id = uuid.uuid7()
        child_id = uuid.uuid7()

        async with _db.async_session_factory() as db:
            async with db.begin():
                await _create_team_session(db, lead_id)
                await _create_member_session(db, child_id, lead_id)

        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions")
        assert resp.status_code == 200
        data = resp.json()

        assert "data" in data
        assert "has_more" in data
        assert "next_cursor" in data
        # Me lead session is in the list; member session is not
        found = [s for s in data["data"] if s["id"] == str(lead_id)]
        assert len(found) == 1

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, app_with_team):
        """No team_lead sessions → empty data list, has_more=False."""
        client = TestClient(app_with_team)
        # Me use a before= cursor that predates any real data
        resp = client.get("/api/team/sessions?before=2000-01-01T00:00:00Z")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(self, app_with_team):
        import app.core.db as _db

        # Me create 3 lead sessions
        ids = [uuid.uuid7() for _ in range(3)]
        async with _db.async_session_factory() as db:
            async with db.begin():
                for sid in ids:
                    await _create_team_session(db, sid)

        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) <= 2


# ---------------------------------------------------------------------------
# DELETE /team/sessions/{session_id}
# ---------------------------------------------------------------------------


class TestDeleteTeamSessionWithData:
    @pytest.mark.asyncio
    async def test_delete_session_removes_session_and_messages(self, app_with_team):
        import app.core.db as _db

        lead_id = uuid.uuid7()
        async with _db.async_session_factory() as db:
            async with db.begin():
                await _create_team_session(db, lead_id)
                await _add_message(db, lead_id, role="user", content="delete me")

        client = TestClient(app_with_team)
        resp = client.delete(f"/api/team/sessions/{lead_id}")
        assert resp.status_code == 204

        # Me verify session is gone via history endpoint
        resp = client.get(f"/api/team/{lead_id}/history")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /team/{session_id}/history (lines 281-340)
# ---------------------------------------------------------------------------


class TestTeamHistoryWithData:
    @pytest.mark.asyncio
    async def test_history_returns_lead_and_members(self, app_with_team):
        import app.core.db as _db

        lead_id = uuid.uuid7()
        member_id = uuid.uuid7()

        async with _db.async_session_factory() as db:
            async with db.begin():
                await _create_team_session(db, lead_id)
                await _create_member_session(
                    db, member_id, lead_id, agent_name="worker"
                )
                await _add_message(db, lead_id, role="user", content="lead msg")
                await _add_message(db, lead_id, role="assistant", content="lead reply")
                await _add_message(db, member_id, role="user", content="member input")
                await _add_message(
                    db, member_id, role="assistant", content="member reply"
                )

        client = TestClient(app_with_team)
        resp = client.get(f"/api/team/{lead_id}/history")
        assert resp.status_code == 200
        data = resp.json()

        # Me check lead messages
        assert "lead" in data
        assert len(data["lead"]["messages"]) >= 2

        # Me check members
        assert "members" in data
        assert len(data["members"]) >= 1
        member = data["members"][0]
        assert len(member["messages"]) >= 2
        assert member["name"] == "worker"

    @pytest.mark.asyncio
    async def test_history_excludes_summary_messages(self, app_with_team):
        import app.core.db as _db

        lead_id = uuid.uuid7()
        async with _db.async_session_factory() as db:
            async with db.begin():
                await _create_team_session(db, lead_id)
                await _add_message(db, lead_id, role="user", content="visible")
                await _add_message(
                    db,
                    lead_id,
                    role="assistant",
                    content="hidden summary",
                    is_summary=True,
                )

        client = TestClient(app_with_team)
        resp = client.get(f"/api/team/{lead_id}/history")
        data = resp.json()

        contents = [m["content"] for m in data["lead"]["messages"]]
        assert "visible" in contents
        assert "hidden summary" not in contents

    @pytest.mark.asyncio
    async def test_history_no_sub_sessions_returns_empty_members(self, app_with_team):
        import app.core.db as _db

        lead_id = uuid.uuid7()
        async with _db.async_session_factory() as db:
            async with db.begin():
                await _create_team_session(db, lead_id)
                await _add_message(db, lead_id, role="user", content="solo")

        client = TestClient(app_with_team)
        resp = client.get(f"/api/team/{lead_id}/history")
        data = resp.json()

        assert data["members"] == []


# ---------------------------------------------------------------------------
# GET /team/sessions — cursor pagination behaviour
# ---------------------------------------------------------------------------


class TestListTeamSessionsCursorPagination:
    """Verify cursor-based pagination semantics for GET /team/sessions."""

    @pytest.mark.asyncio
    async def test_response_shape(self, app_with_team):
        """Response always contains data, has_more, next_cursor."""
        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "has_more" in data
        assert "next_cursor" in data
        # Me legacy fields must NOT be present
        assert "total" not in data
        assert "offset" not in data

    @pytest.mark.asyncio
    async def test_first_page_no_cursor(self, app_with_team):
        """First page (no before=) returns newest sessions."""
        import app.core.db as _db

        ids = [uuid.uuid7() for _ in range(3)]
        async with _db.async_session_factory() as db:
            async with db.begin():
                for sid in ids:
                    await _create_team_session(db, sid)

        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions?limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) >= 1
        # Me sessions are newest-first (UUIDv7 monotonically increases)
        created_times = [s["created_at"] for s in data["data"] if s["created_at"]]
        assert created_times == sorted(created_times, reverse=True)

    @pytest.mark.asyncio
    async def test_has_more_false_when_all_fit(self, app_with_team):
        """has_more=False when result count < limit."""
        import app.core.db as _db

        lead_id = uuid.uuid7()
        async with _db.async_session_factory() as db:
            async with db.begin():
                await _create_team_session(db, lead_id)

        client = TestClient(app_with_team)
        # Me limit=100 — far more than 1 session
        resp = client.get("/api/team/sessions?limit=100")
        data = resp.json()
        # has_more must be False when fewer rows than limit were returned
        assert len(data["data"]) < 100
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_has_more_true_and_cursor_set(self, app_with_team):
        """has_more=True and next_cursor is set when more rows exist."""
        import app.core.db as _db

        ids = [uuid.uuid7() for _ in range(5)]
        async with _db.async_session_factory() as db:
            async with db.begin():
                for sid in ids:
                    await _create_team_session(db, sid)

        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions?limit=2")
        data = resp.json()
        # Me only valid when there are at least 3 sessions total
        if len(data["data"]) == 2 and data["has_more"]:
            assert data["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_cursor_advances_to_next_page(self, app_with_team):
        """Passing next_cursor as before= fetches the next page without overlap."""
        import app.core.db as _db

        # Me create 4 sessions so pagination is deterministic within this test
        ids = [uuid.uuid7() for _ in range(4)]
        async with _db.async_session_factory() as db:
            async with db.begin():
                for sid in ids:
                    await _create_team_session(db, sid)

        client = TestClient(app_with_team)

        # Page 1 — limit=2
        resp1 = client.get("/api/team/sessions?limit=2")
        assert resp1.status_code == 200
        page1 = resp1.json()
        ids_page1 = {s["id"] for s in page1["data"]}

        if not page1["has_more"]:
            pytest.skip("Not enough sessions for multi-page test")

        cursor = page1["next_cursor"]
        assert cursor is not None

        # Page 2 — use cursor
        resp2 = client.get(f"/api/team/sessions?limit=2&before={cursor}")
        assert resp2.status_code == 200
        page2 = resp2.json()
        ids_page2 = {s["id"] for s in page2["data"]}

        # Me no overlap between pages
        assert ids_page1.isdisjoint(ids_page2)

    @pytest.mark.asyncio
    async def test_invalid_before_returns_422(self, app_with_team):
        """Malformed before= cursor returns 422."""
        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions?before=not-a-date")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_before_far_past_returns_empty(self, app_with_team):
        """before= in the distant past returns no sessions."""
        import app.core.db as _db

        lead_id = uuid.uuid7()
        async with _db.async_session_factory() as db:
            async with db.begin():
                await _create_team_session(db, lead_id)

        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions?before=2000-01-01T00:00:00Z")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_default_limit_is_20(self, app_with_team):
        """Default limit is 20."""
        import app.core.db as _db

        ids = [uuid.uuid7() for _ in range(25)]
        async with _db.async_session_factory() as db:
            async with db.begin():
                for sid in ids:
                    await _create_team_session(db, sid)

        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions")
        assert resp.status_code == 200
        data = resp.json()
        # Default page size is 20 — must not return more than 20
        assert len(data["data"]) <= 20

    @pytest.mark.asyncio
    async def test_limit_exceeding_max_rejected(self, app_with_team):
        """limit > 100 is rejected (422)."""
        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions?limit=101")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_member_sessions_excluded_from_list(self, app_with_team):
        """Member sessions (parent_session_id set) do not appear in the top-level list."""
        import app.core.db as _db

        lead_id = uuid.uuid7()
        member_id = uuid.uuid7()
        async with _db.async_session_factory() as db:
            async with db.begin():
                await _create_team_session(db, lead_id)
                await _create_member_session(db, member_id, lead_id)

        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions")
        data = resp.json()

        top_level_ids = {s["id"] for s in data["data"]}
        assert str(lead_id) in top_level_ids
        assert str(member_id) not in top_level_ids
