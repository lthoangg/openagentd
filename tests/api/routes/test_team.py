"""Tests for app/api/routes/team.py — team endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agent.agent_loop import Agent
from app.agent.providers.base import LLMProviderBase
from app.agent.mode.team.member import TeamLead, TeamMember
from app.agent.mode.team.team import AgentTeam


class MockTestProvider(LLMProviderBase):
    """Mock LLM provider."""

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
    """Create a test team (not started)."""
    agent_lead = Agent(
        name="lead", llm_provider=MockTestProvider(), system_prompt="Lead"
    )
    agent_worker = Agent(
        name="worker", llm_provider=MockTestProvider(), system_prompt="Worker"
    )

    lead = TeamLead(agent_lead)
    worker = TeamMember(agent_worker)

    team = AgentTeam(lead=lead, members={"worker": worker})
    return team


@pytest.fixture
def app_with_team(test_team):
    """Create FastAPI app with team attached."""
    from app.api.app import create_app
    from app.services.team_manager import set_team

    app = create_app()
    set_team(test_team)
    yield app
    set_team(None)


@pytest.fixture
def app_without_team():
    """Create FastAPI app without team."""
    from app.api.app import create_app
    from app.services.team_manager import set_team

    app = create_app()
    set_team(None)
    return app


class TestTeamChatRoute:
    """Test POST /team/chat endpoint."""

    def test_team_chat_no_team_returns_404(self, app_without_team):
        client = TestClient(app_without_team)
        response = client.post("/api/team/chat", data={"message": "Hello"})
        assert response.status_code == 404
        assert "No agent team" in response.json()["detail"]

    def test_team_chat_returns_202(self, app_with_team, test_team):
        test_team.handle_user_message = AsyncMock(return_value=str(uuid.uuid7()))
        client = TestClient(app_with_team)
        response = client.post("/api/team/chat", data={"message": "Hello team"})
        assert response.status_code == 202

    def test_team_chat_returns_session_id(self, app_with_team, test_team):
        sid = str(uuid.uuid7())
        test_team.handle_user_message = AsyncMock(return_value=sid)
        client = TestClient(app_with_team)
        response = client.post("/api/team/chat", data={"message": "Hello"})
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "accepted"

    def test_team_chat_with_provided_session_id(self, app_with_team, test_team):
        session_id = str(uuid.uuid7())
        test_team.handle_user_message = AsyncMock(return_value=session_id)
        client = TestClient(app_with_team)
        response = client.post(
            "/api/team/chat", data={"message": "Hello", "session_id": session_id}
        )
        data = response.json()
        assert data["session_id"] == session_id

    def test_team_chat_generates_session_id_when_omitted(
        self, app_with_team, test_team
    ):
        test_team.handle_user_message = AsyncMock(return_value=str(uuid.uuid7()))
        client = TestClient(app_with_team)
        response = client.post("/api/team/chat", data={"message": "Hello"})
        uuid.UUID(response.json()["session_id"])  # Should not raise

    def test_team_chat_interrupt_flag(self, app_with_team, test_team):
        """Interrupt-only (no message) returns 202 with status=interrupted."""
        client = TestClient(app_with_team)
        sid = str(uuid.uuid7())
        response = client.post(
            "/api/team/chat", data={"interrupt": "true", "session_id": sid}
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "interrupted"
        assert data["session_id"] == sid

    def test_team_chat_interrupt_with_message_rejected(self, app_with_team, test_team):
        """Interrupt + message is mutually exclusive — 422."""
        client = TestClient(app_with_team)
        response = client.post(
            "/api/team/chat",
            data={
                "message": "Redirect",
                "interrupt": "true",
                "session_id": str(uuid.uuid7()),
            },
        )
        assert response.status_code == 422

    def test_team_chat_calls_handle_user_message(self, app_with_team, test_team):
        test_team.handle_user_message = AsyncMock(return_value=str(uuid.uuid7()))
        client = TestClient(app_with_team)
        response = client.post("/api/team/chat", data={"message": "Hello team"})
        assert response.status_code == 202
        test_team.handle_user_message.assert_awaited_once()
        assert test_team.handle_user_message.call_args.kwargs["content"] == "Hello team"

    def test_team_chat_message_validation_empty_raises(self, app_with_team):
        client = TestClient(app_with_team)
        response = client.post("/api/team/chat", data={"message": ""})
        assert response.status_code == 422

    def test_team_chat_message_validation_missing_raises(self, app_with_team):
        client = TestClient(app_with_team)
        response = client.post("/api/team/chat", data={"session_id": str(uuid.uuid7())})
        assert response.status_code == 422


class TestTeamStreamRoute:
    """Test GET /team/{session_id}/stream endpoint."""

    @pytest.mark.asyncio
    async def test_team_stream_returns_sse_events(self, app_with_team):
        """GET /team/{session_id}/stream attaches to the stream store."""
        from httpx import ASGITransport, AsyncClient

        session_id = str(uuid.uuid7())

        async def mock_attach(sid):
            yield {
                "event": "message",
                "data": '{"type":"message","agent":"lead","text":"hi"}',
            }

        with patch(
            "app.services.memory_stream_store.attach",
            return_value=mock_attach(session_id),
        ):
            transport = ASGITransport(app=app_with_team)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get(f"/api/team/{session_id}/stream")
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")


class TestTeamAgentsRoute:
    """Test GET /team/agents endpoint."""

    def test_team_agents_no_team_returns_404(self, app_without_team):
        client = TestClient(app_without_team)
        response = client.get("/api/team/agents")
        assert response.status_code == 404

    def test_team_agents_returns_200(self, app_with_team):
        client = TestClient(app_with_team)
        response = client.get("/api/team/agents")
        assert response.status_code == 200

    def test_team_agents_returns_agents_list(self, app_with_team):
        client = TestClient(app_with_team)
        data = client.get("/api/team/agents").json()
        assert "agents" in data
        names = {a["name"] for a in data["agents"]}
        assert "lead" in names
        assert "worker" in names

    def test_team_agents_includes_is_lead(self, app_with_team):
        client = TestClient(app_with_team)
        data = client.get("/api/team/agents").json()
        lead_entry = next(a for a in data["agents"] if a["name"] == "lead")
        assert lead_entry["is_lead"] is True
        worker_entry = next(a for a in data["agents"] if a["name"] == "worker")
        assert worker_entry["is_lead"] is False


class TestTeamHistoryRoute:
    """Test GET /team/{session_id}/history endpoint."""

    def test_team_history_no_team_returns_404(self, app_without_team):
        client = TestClient(app_without_team)
        response = client.get(f"/api/team/{uuid.uuid7()}/history")
        assert response.status_code == 404

    def test_team_history_requires_session_id(self, app_with_team):
        client = TestClient(app_with_team)
        # Without session_id path param the route doesn't match → SPA catch-all
        # may return 200 (index.html) or 404 depending on whether web UI is built
        response = client.get("/api/team/history")
        assert response.status_code in (200, 404)

    def test_team_history_session_not_found_returns_404(self, app_with_team):
        client = TestClient(app_with_team)
        response = client.get(f"/api/team/{uuid.uuid7()}/history")
        assert response.status_code == 404


class TestTeamChatFormValidation:
    """Test POST /team/chat form validation (FastAPI Form() params)."""

    def test_empty_message_returns_422(self, app_with_team):
        client = TestClient(app_with_team)
        response = client.post("/api/team/chat", data={"message": ""})
        assert response.status_code == 422

    def test_missing_message_returns_422(self, app_with_team):
        client = TestClient(app_with_team)
        response = client.post("/api/team/chat", data={})
        assert response.status_code == 422
