"""Tests for _try_emit_done with mixed agent states.

Covers:
- Done emission when lead + all members are available or error
- No done emission when any agent is working
- Done flag reset after emission
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.agent_loop import Agent
from app.agent.mode.team.member import TeamLead, TeamMember
from app.agent.mode.team.team import AgentTeam
from tests.agent.mode.team.conftest import MockTeamProvider


def _make_db_factory():
    """Create a mock async session factory."""
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_db.add = MagicMock()
    mock_db.exec = AsyncMock(
        return_value=MagicMock(
            all=MagicMock(return_value=[]),
            first=MagicMock(return_value=None),
        )
    )

    @asynccontextmanager
    async def factory():
        yield mock_db

    return factory


def _make_agent(name):
    """Create a mock agent."""
    return Agent(name=name, llm_provider=MockTeamProvider(), system_prompt=name)


def _make_team():
    """Create a test team."""
    lead_agent = _make_agent("lead")
    member_agent = _make_agent("worker")
    db_factory = _make_db_factory()
    lead = TeamLead(lead_agent, session_id="lead-sid", db_factory=db_factory)
    member = TeamMember(member_agent, session_id="worker-sid", db_factory=db_factory)
    team = AgentTeam(lead=lead, members={"worker": member})
    return team


class TestDoneDetectionMixedStates:
    """Test _try_emit_done with various state combinations."""

    @pytest.mark.asyncio
    async def test_done_emits_when_lead_available_member_error(self):
        """Lead available + member error → done fires."""
        team = _make_team()
        team._has_active_turn = True
        team.lead.state = "available"
        team.members["worker"].state = "error"

        pushed = []

        async def fake_push(sid, event):
            pushed.append(event)

        with patch("app.services.memory_stream_store.push_event", new=fake_push):
            with patch(
                "app.services.memory_stream_store.mark_done", new_callable=AsyncMock
            ):
                await team._try_emit_done()

        # Should have emitted done
        assert len(pushed) == 1
        assert pushed[0].event == "done"

    @pytest.mark.asyncio
    async def test_done_emits_when_lead_error_member_available(self):
        """Lead error + member available → done fires."""
        team = _make_team()
        team._has_active_turn = True
        team.lead.state = "error"
        team.members["worker"].state = "available"

        pushed = []

        async def fake_push(sid, event):
            pushed.append(event)

        with patch("app.services.memory_stream_store.push_event", new=fake_push):
            with patch(
                "app.services.memory_stream_store.mark_done", new_callable=AsyncMock
            ):
                await team._try_emit_done()

        # Should have emitted done
        assert len(pushed) == 1
        assert pushed[0].event == "done"

    @pytest.mark.asyncio
    async def test_done_not_emits_when_lead_working_member_error(self):
        """Lead working + member error → no done."""
        team = _make_team()
        team._has_active_turn = True
        team.lead.state = "working"
        team.members["worker"].state = "error"

        pushed = []

        async def fake_push(sid, event):
            pushed.append(event)

        with patch("app.services.memory_stream_store.push_event", new=fake_push):
            with patch(
                "app.services.memory_stream_store.mark_done", new_callable=AsyncMock
            ):
                await team._try_emit_done()

        # Should NOT have emitted done
        assert len(pushed) == 0

    @pytest.mark.asyncio
    async def test_done_not_emits_when_any_working(self):
        """Any agent working → no done."""
        team = _make_team()
        team._has_active_turn = True
        team.lead.state = "available"
        team.members["worker"].state = "working"

        pushed = []

        async def fake_push(sid, event):
            pushed.append(event)

        with patch("app.services.memory_stream_store.push_event", new=fake_push):
            with patch(
                "app.services.memory_stream_store.mark_done", new_callable=AsyncMock
            ):
                await team._try_emit_done()

        # Should NOT have emitted done
        assert len(pushed) == 0

    @pytest.mark.asyncio
    async def test_done_flag_not_double_reset(self):
        """After done fires, second call is no-op (flag already false)."""
        team = _make_team()
        team._has_active_turn = True
        team.lead.state = "available"
        team.members["worker"].state = "available"

        pushed = []

        async def fake_push(sid, event):
            pushed.append(event)

        with patch("app.services.memory_stream_store.push_event", new=fake_push):
            with patch(
                "app.services.memory_stream_store.mark_done", new_callable=AsyncMock
            ):
                await team._try_emit_done()

        # First call should emit done
        assert len(pushed) == 1
        assert team._has_active_turn is False

        # Second call should be no-op
        pushed.clear()
        with patch("app.services.memory_stream_store.push_event", new=fake_push):
            with patch(
                "app.services.memory_stream_store.mark_done", new_callable=AsyncMock
            ):
                await team._try_emit_done()

        # Should not have emitted again
        assert len(pushed) == 0

    @pytest.mark.asyncio
    async def test_done_not_emits_when_no_active_turn(self):
        """When _has_active_turn is False, done is not emitted."""
        team = _make_team()
        team._has_active_turn = False
        team.lead.state = "available"
        team.members["worker"].state = "available"

        pushed = []

        async def fake_push(sid, event):
            pushed.append(event)

        with patch("app.services.memory_stream_store.push_event", new=fake_push):
            with patch(
                "app.services.memory_stream_store.mark_done", new_callable=AsyncMock
            ):
                await team._try_emit_done()

        # Should not emit when no active turn
        assert len(pushed) == 0

    @pytest.mark.asyncio
    async def test_done_emits_when_both_error(self):
        """Lead error + member error → done fires."""
        team = _make_team()
        team._has_active_turn = True
        team.lead.state = "error"
        team.members["worker"].state = "error"

        pushed = []

        async def fake_push(sid, event):
            pushed.append(event)

        with patch("app.services.memory_stream_store.push_event", new=fake_push):
            with patch(
                "app.services.memory_stream_store.mark_done", new_callable=AsyncMock
            ):
                await team._try_emit_done()

        # Should have emitted done (both are done, even if error)
        assert len(pushed) == 1
        assert pushed[0].event == "done"

    @pytest.mark.asyncio
    async def test_done_emits_when_both_available(self):
        """Lead available + member available → done fires."""
        team = _make_team()
        team._has_active_turn = True
        team.lead.state = "available"
        team.members["worker"].state = "available"

        pushed = []

        async def fake_push(sid, event):
            pushed.append(event)

        with patch("app.services.memory_stream_store.push_event", new=fake_push):
            with patch(
                "app.services.memory_stream_store.mark_done", new_callable=AsyncMock
            ):
                await team._try_emit_done()

        # Should have emitted done
        assert len(pushed) == 1
        assert pushed[0].event == "done"

    @pytest.mark.asyncio
    async def test_done_swallows_error(self):
        """Stream store error during done emission is swallowed."""
        team = _make_team()
        team._has_active_turn = True
        team.lead.state = "available"
        team.members["worker"].state = "available"

        async def fake_push(sid, event):
            raise ConnectionError("stream down")

        with patch("app.services.memory_stream_store.push_event", new=fake_push):
            with patch(
                "app.services.memory_stream_store.mark_done", new_callable=AsyncMock
            ):
                # Must not raise
                await team._try_emit_done()

        # Flag should still be reset
        assert team._has_active_turn is False
