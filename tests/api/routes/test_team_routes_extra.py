"""Extra tests for app/api/routes/team.py — covers sessions, delete, agents, history."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agent.agent_loop import Agent
from app.agent.providers.base import LLMProviderBase
from app.agent.mode.team.member import TeamLead, TeamMember
from app.agent.mode.team.team import AgentTeam


class MockProvider(LLMProviderBase):
    model = "mock"

    def stream(self, messages, tools=None, **kwargs):
        async def gen():
            from app.agent.schemas.chat import (
                ChatCompletionChunk,
                ChatCompletionChunkChoice,
                ChatCompletionDelta,
            )

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


@pytest.fixture
def app_without_team():
    from app.api.app import create_app
    from app.services.team_manager import set_team

    app = create_app()
    set_team(None)
    return app


# ---------------------------------------------------------------------------
# GET /team/agents (lines 143-160)
# ---------------------------------------------------------------------------


class TestTeamAgentsRouteExtra:
    def test_agents_no_team_returns_404(self, app_without_team):
        client = TestClient(app_without_team)
        assert client.get("/api/team/agents").status_code == 404

    def test_agents_returns_lead_and_members(self, app_with_team):
        client = TestClient(app_with_team)
        resp = client.get("/api/team/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        names = [a["name"] for a in data["agents"]]
        assert "lead" in names
        assert "worker" in names

    def test_agents_lead_has_is_lead_true(self, app_with_team):
        client = TestClient(app_with_team)
        data = client.get("/api/team/agents").json()
        lead_entry = next(a for a in data["agents"] if a["name"] == "lead")
        assert lead_entry["is_lead"] is True

    def test_agents_worker_has_is_lead_false(self, app_with_team):
        client = TestClient(app_with_team)
        data = client.get("/api/team/agents").json()
        worker_entry = next(a for a in data["agents"] if a["name"] == "worker")
        assert worker_entry["is_lead"] is False

    def test_agents_response_has_tools_and_skills_keys(self, app_with_team):
        client = TestClient(app_with_team)
        data = client.get("/api/team/agents").json()
        for agent in data["agents"]:
            assert "tools" in agent
            assert "skills" in agent
            assert "model" in agent


# ---------------------------------------------------------------------------
# GET /team/sessions (lines 163-215)
# ---------------------------------------------------------------------------


class TestListTeamSessions:
    def test_list_sessions_returns_200(self, app_with_team):
        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "has_more" in data
        assert "next_cursor" in data
        # Me legacy offset/total fields must not be present
        assert "total" not in data
        assert "offset" not in data

    def test_list_sessions_limit_param(self, app_with_team):
        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions?limit=5")
        assert resp.status_code == 200

    def test_list_sessions_invalid_limit_returns_422(self, app_with_team):
        client = TestClient(app_with_team)
        resp = client.get("/api/team/sessions?limit=0")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /team/sessions/{session_id}
# ---------------------------------------------------------------------------


class TestDeleteTeamSession:
    def test_delete_session_not_found_returns_404(self, app_with_team):
        client = TestClient(app_with_team)
        resp = client.delete(f"/api/team/sessions/{uuid.uuid7()}")
        assert resp.status_code == 404

    def test_delete_session_invalid_uuid_returns_422(self, app_with_team):
        client = TestClient(app_with_team)
        resp = client.delete("/api/team/sessions/bad-uuid")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /team/{session_id}/history (lines 294-338)
# ---------------------------------------------------------------------------


class TestTeamHistoryRouteExtra:
    def test_history_no_team_returns_404(self, app_without_team):
        client = TestClient(app_without_team)
        resp = client.get(f"/api/team/{uuid.uuid7()}/history")
        assert resp.status_code == 404

    def test_history_session_not_found_returns_404(self, app_with_team):
        client = TestClient(app_with_team)
        resp = client.get(f"/api/team/{uuid.uuid7()}/history")
        assert resp.status_code == 404

    def test_history_valid_unknown_uuid_returns_404(self, app_with_team):
        client = TestClient(app_with_team)
        resp = client.get(f"/api/team/{uuid.uuid7()}/history")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# _serialize_agent helper
# ---------------------------------------------------------------------------


class TestSerializeAgent:
    def test_serialize_includes_model_id(self):
        from app.api.routes.team import _serialize_agent
        from app.agent.agent_loop import Agent

        provider = MagicMock()
        agent = Agent(
            llm_provider=provider, name="bot", model_id="openrouter:qwen/qwen3"
        )
        result = _serialize_agent(agent, is_lead=True)
        assert result["model"] == "openrouter:qwen/qwen3"
        assert result["is_lead"] is True
        assert result["name"] == "bot"

    def test_serialize_none_model_id(self):
        from app.api.routes.team import _serialize_agent
        from app.agent.agent_loop import Agent

        provider = MagicMock()
        agent = Agent(llm_provider=provider, name="bot")
        result = _serialize_agent(agent, is_lead=False)
        assert result["model"] is None

    def test_serialize_skills_fallback_on_discover_error(self):
        from app.api.routes.team import _serialize_agent
        from app.agent.agent_loop import Agent

        provider = MagicMock()
        agent = Agent(llm_provider=provider, name="bot", skills=["my-skill"])
        with patch(
            "app.api.routes.team.chat.discover_skills",
            side_effect=Exception("error"),
        ):
            result = _serialize_agent(agent)
        assert result["skills"] == [{"name": "my-skill", "description": ""}]

    def test_serialize_includes_mcp_servers(self):
        """Configured MCP servers surface even when they contribute zero tools.

        The UI uses this list to render server sections (and group their tools
        by the `mcp_<server>_<tool>` naming convention), so servers that exist
        in config but aren't ready still need to round-trip.
        """
        from app.agent.agent_loop import Agent
        from app.api.routes.team import _serialize_agent

        agent = Agent(
            llm_provider=MagicMock(), name="bot", mcp_servers=["context7", "filesystem"]
        )
        result = _serialize_agent(agent)
        assert result["mcp_servers"] == ["context7", "filesystem"]
