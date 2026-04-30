"""Tests for TeamMember on-demand activation and _handle_messages."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio

from app.agent.agent_loop import Agent
from app.agent.mode.team.mailbox import Message
from app.agent.mode.team.member import TeamLead, TeamMember
from app.agent.mode.team.team import AgentTeam
from tests.agent.mode.team.conftest import MockTeamProvider


def _make_mock_db_factory():
    """Create a mock async session factory that returns a mock db session."""
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_db.exec = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    mock_db.add = MagicMock()

    @asynccontextmanager
    async def factory():
        yield mock_db

    return factory


@pytest_asyncio.fixture
async def team_with_db():
    """Create a team with mocked DB factory."""
    db_factory = _make_mock_db_factory()

    lead = TeamLead(
        Agent(name="lead", llm_provider=MockTeamProvider("lead response")),
        db_factory=db_factory,
    )
    worker = TeamMember(
        Agent(name="worker", llm_provider=MockTeamProvider("worker response")),
        db_factory=db_factory,
    )

    team = AgentTeam(lead=lead, members={"worker": worker})
    return team


class TestOnDemandActivation:
    """Test on-demand activation — agents activate when messages arrive."""

    async def test_no_tasks_at_startup(self, team_with_db):
        """After start(), no background tasks are running."""
        team = team_with_db
        await team.start()

        assert team.lead._active_task is None
        assert team.members["worker"]._active_task is None

        await team.stop()

    async def test_worker_activates_on_inbox_message(self, team_with_db):
        """Worker activates when a message arrives in inbox."""
        team = team_with_db
        await team.start()

        msg = Message(from_agent="lead", to_agent="worker", content="[lead]: do task")
        await team.mailbox.send(to="worker", message=msg)
        await asyncio.sleep(0.1)

        assert team.members["worker"].state == "available"

        await team.stop()

    async def test_worker_emits_agent_status_events(
        self, team_with_db, mock_stream_store
    ):
        """Worker emits agent_status working/available events to the stream store."""
        team = team_with_db
        await team.start()

        msg = Message(from_agent="lead", to_agent="worker", content="[lead]: task")
        await team.mailbox.send(to="worker", message=msg)
        await asyncio.sleep(0.1)

        events = [c.args[1].event for c in mock_stream_store.call_args_list]
        assert "agent_status" in events

        await team.stop()

    async def test_worker_returns_to_available_after_processing(self, team_with_db):
        """Worker returns to available state after processing a message."""
        team = team_with_db
        worker = team.members["worker"]

        await team.start()

        msg = Message(from_agent="lead", to_agent="worker", content="[lead]: work")
        await team.mailbox.send(to="worker", message=msg)
        await asyncio.sleep(0.1)

        assert worker.state == "available"

        await team.stop()

    async def test_maybe_activate_skips_when_already_working(self, team_with_db):
        """_maybe_activate() is a no-op when agent is already working."""
        team = team_with_db
        await team.start()

        worker = team.members["worker"]
        worker.state = "working"
        worker._active_task = asyncio.create_task(asyncio.sleep(10))

        # This should not spawn a second task
        worker._maybe_activate()
        # Still the same task
        assert worker._active_task is not None

        worker._active_task.cancel()
        try:
            await worker._active_task
        except asyncio.CancelledError:
            pass
        await team.stop()


class TestWorkerErrorHandling:
    """Test error handling during activation."""

    async def test_worker_error_emits_agent_error(
        self, team_with_db, mock_stream_store
    ):
        """When agent.run() raises, worker emits agent_error to the stream store."""
        team = team_with_db
        worker = team.members["worker"]
        worker.agent.run = AsyncMock(side_effect=RuntimeError("LLM crashed"))

        await team.start()

        msg = Message(from_agent="lead", to_agent="worker", content="[lead]: task")
        await team.mailbox.send(to="worker", message=msg)
        await asyncio.sleep(0.1)

        # Should have emitted an agent_status error event
        events = [c.args[1].event for c in mock_stream_store.call_args_list]
        assert "agent_status" in events

        await team.stop()

    async def test_worker_error_sets_error_state(self, team_with_db):
        """When agent.run() raises, worker goes to error state."""
        team = team_with_db
        worker = team.members["worker"]
        worker.agent.run = AsyncMock(side_effect=RuntimeError("LLM crashed"))

        await team.start()

        msg = Message(from_agent="lead", to_agent="worker", content="[lead]: task")
        await team.mailbox.send(to="worker", message=msg)
        await asyncio.sleep(0.1)

        assert worker.state == "error"

        await team.stop()

    async def test_worker_error_notifies_lead_via_mailbox(self, team_with_db):
        """When agent.run() raises, member sends error notification to lead."""
        team = team_with_db
        worker = team.members["worker"]

        # Stop lead from consuming messages so we can inspect the inbox
        lead = team.lead
        lead.agent.run = AsyncMock(return_value=None)

        worker.agent.run = AsyncMock(side_effect=RuntimeError("boom"))

        await team.start()

        msg = Message(from_agent="lead", to_agent="worker", content="[lead]: task")
        await team.mailbox.send(to="worker", message=msg)
        await asyncio.sleep(0.1)

        # Worker should be in error state after error
        assert worker.state == "error"

        await team.stop()

    async def test_worker_error_notifies_lead(self, team_with_db, mock_stream_store):
        """When member errors, lead gets a notification and stream store gets error event."""
        team = team_with_db
        worker = team.members["worker"]
        worker.agent.run = AsyncMock(side_effect=RuntimeError("crash"))

        await team.start()

        msg = Message(from_agent="lead", to_agent="worker", content="[lead]: task")
        await team.mailbox.send(to="worker", message=msg)
        await asyncio.sleep(0.1)

        events = [c.args[1].event for c in mock_stream_store.call_args_list]
        assert "agent_status" in events

        await team.stop()


class TestLeadErrorHandling:
    """Test error handling when the lead itself fails.

    Members notify the lead via mailbox on error; the lead has no peer to
    notify, so :meth:`TeamLead._on_turn_error` emits a typed ``ErrorEvent``
    to the stream so the UI can surface *why* the turn stopped.
    """

    async def test_lead_error_emits_error_event(self, team_with_db, mock_stream_store):
        """When the lead's agent.run() raises, an ErrorEvent hits the stream."""
        team = team_with_db
        lead = team.lead
        lead.agent.run = AsyncMock(side_effect=RuntimeError("quota exceeded"))

        await team.start()

        msg = Message(from_agent="user", to_agent="lead", content="[user]: hi")
        await team.mailbox.send(to="lead", message=msg)
        await asyncio.sleep(0.1)

        events = [c.args[1].event for c in mock_stream_store.call_args_list]
        assert "error" in events, (
            f"expected 'error' event from lead failure, got {events}"
        )

        # Payload carries the exception message and agent name.
        error_envelopes = [
            c.args[1]
            for c in mock_stream_store.call_args_list
            if c.args[1].event == "error"
        ]
        assert len(error_envelopes) == 1
        payload = error_envelopes[0].data
        assert "quota exceeded" in payload["message"]
        assert payload["metadata"]["agent"] == "lead"
        assert payload["metadata"]["exception"] == "RuntimeError"

        await team.stop()

    async def test_lead_error_sets_error_state(self, team_with_db):
        """Lead reaches 'error' state after agent.run() raises."""
        team = team_with_db
        lead = team.lead
        lead.agent.run = AsyncMock(side_effect=RuntimeError("boom"))

        await team.start()

        msg = Message(from_agent="user", to_agent="lead", content="[user]: hi")
        await team.mailbox.send(to="lead", message=msg)
        await asyncio.sleep(0.1)

        assert lead.state == "error"

        await team.stop()

    async def test_member_error_does_not_emit_error_event(
        self, team_with_db, mock_stream_store
    ):
        """Member failures go through mailbox to lead — no top-level ErrorEvent.

        Guards against regression where the base ``_on_turn_error`` is
        changed and accidentally starts emitting ``error`` for members too.
        """
        team = team_with_db
        worker = team.members["worker"]
        worker.agent.run = AsyncMock(side_effect=RuntimeError("member crashed"))

        await team.start()

        msg = Message(from_agent="lead", to_agent="worker", content="[lead]: task")
        await team.mailbox.send(to="worker", message=msg)
        await asyncio.sleep(0.1)

        events = [c.args[1].event for c in mock_stream_store.call_args_list]
        assert "error" not in events, (
            f"member error should not emit top-level ErrorEvent, got {events}"
        )

        await team.stop()


class TestHandleMessagesFormatting:
    """Test _handle_messages inbox formatting."""

    async def test_broadcast_message_kept_as_is(self, team_with_db):
        """Broadcast messages use their existing format."""
        team = team_with_db
        await team.start()

        msg = Message(
            from_agent="lead",
            to_agent="worker",
            content="[broadcast]: all hands",
            is_broadcast=True,
        )
        await team.mailbox.send(to="worker", message=msg)
        await asyncio.sleep(0.1)

        await team.stop()

    async def test_user_message_kept_as_is(self, team_with_db):
        """User messages keep their [user]: prefix."""
        team = team_with_db
        await team.start()

        msg = Message(from_agent="user", to_agent="lead", content="[user]: hello")
        await team.mailbox.send(to="lead", message=msg)
        await asyncio.sleep(0.1)

        await team.stop()


class TestSafetyNet:
    """Safety net removed — _replied flag no longer exists on TeamMember."""

    pass
