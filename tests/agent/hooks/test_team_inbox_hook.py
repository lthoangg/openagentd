"""Tests for TeamInboxHook — drains mailbox before each LLM call."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.mode.team.hooks.team_inbox import TeamInboxHook
from app.agent.mode.team.mailbox import Message, TeamMailbox
from app.agent.schemas.chat import HumanMessage
from app.agent.state import AgentState, ModelRequest, RunContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ctx() -> RunContext:
    """Create a test RunContext."""
    return RunContext(session_id="test-session", run_id="test-run", agent_name="bot")


def make_state(messages: list | None = None) -> AgentState:
    """Create a test AgentState."""
    if messages is None:
        messages = []
    return AgentState(messages=messages, system_prompt="Test prompt")


def make_request(messages: tuple | None = None) -> ModelRequest:
    """Create a test ModelRequest."""
    if messages is None:
        messages = ()
    return ModelRequest(messages=messages, system_prompt="Test prompt")


def make_message(
    from_agent: str = "agent_a",
    to_agent: str | None = "agent_b",
    content: str = "Hello",
) -> Message:
    """Create a test Message."""
    return Message(from_agent=from_agent, to_agent=to_agent, content=content)


def make_human_message(content: str = "Hello") -> HumanMessage:
    """Create a test HumanMessage."""
    return HumanMessage(content=content)


def _mock_member(name: str = "test_agent") -> MagicMock:
    """Create a mock TeamMemberBase with required attributes and methods."""
    member = MagicMock()
    member.name = name
    member._mailbox = TeamMailbox()
    member._mailbox.register(name)
    member._team = MagicMock()
    member._team._emit = AsyncMock()  # _emit is async
    member._persist_inbox = AsyncMock()
    member._should_emit_inbox_sse = MagicMock(return_value=True)
    return member


# ---------------------------------------------------------------------------
# Test: Empty inbox returns None
# ---------------------------------------------------------------------------


class TestEmptyInbox:
    """Test behavior when mailbox has no messages."""

    @pytest.mark.asyncio
    async def test_empty_inbox_returns_none(self):
        """When mailbox is empty, before_model returns None."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        result = await hook.before_model(ctx, state, request)

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_inbox_does_not_modify_state(self):
        """When mailbox is empty, state.messages is unchanged."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        ctx = make_ctx()
        initial_messages = [make_human_message("existing")]
        state = make_state(initial_messages)
        request = make_request()

        await hook.before_model(ctx, state, request)

        assert state.messages == initial_messages

    @pytest.mark.asyncio
    async def test_empty_inbox_does_not_call_persist(self):
        """When mailbox is empty, _persist_inbox is not called."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        await hook.before_model(ctx, state, request)

        member._persist_inbox.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_inbox_does_not_emit_sse(self):
        """When mailbox is empty, _team._emit is not called."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        await hook.before_model(ctx, state, request)

        member._team._emit.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Messages are drained and injected
# ---------------------------------------------------------------------------


class TestMessageDrainAndInject:
    """Test that messages are drained from mailbox and injected into state."""

    @pytest.mark.asyncio
    async def test_single_message_drained_and_injected(self):
        """A single message is drained and appended to state.messages."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        # Queue a message
        msg = make_message(from_agent="agent_b", content="Hello from B")
        await member._mailbox.send(to="agent_a", message=msg)

        # Mock _persist_inbox to return a HumanMessage
        persisted_msg = make_human_message("Hello from B")
        member._persist_inbox.return_value = [persisted_msg]

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        await hook.before_model(ctx, state, request)

        # Message should be appended to state
        assert len(state.messages) == 1
        assert state.messages[0].content == "Hello from B"

    @pytest.mark.asyncio
    async def test_multiple_messages_drained_in_order(self):
        """Multiple messages are drained and appended in order."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        # Queue 3 messages
        msg1 = make_message(from_agent="agent_b", content="First")
        msg2 = make_message(from_agent="agent_c", content="Second")
        msg3 = make_message(from_agent="agent_b", content="Third")

        await member._mailbox.send(to="agent_a", message=msg1)
        await member._mailbox.send(to="agent_a", message=msg2)
        await member._mailbox.send(to="agent_a", message=msg3)

        # Mock _persist_inbox to return HumanMessages
        persisted_msgs = [
            make_human_message("First"),
            make_human_message("Second"),
            make_human_message("Third"),
        ]
        member._persist_inbox.return_value = persisted_msgs

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        await hook.before_model(ctx, state, request)

        # All messages should be appended in order
        assert len(state.messages) == 3
        assert state.messages[0].content == "First"
        assert state.messages[1].content == "Second"
        assert state.messages[2].content == "Third"

    @pytest.mark.asyncio
    async def test_persist_inbox_called_with_drained_messages(self):
        """_persist_inbox is called with the drained messages."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        msg1 = make_message(from_agent="agent_b", content="First")
        msg2 = make_message(from_agent="agent_c", content="Second")

        await member._mailbox.send(to="agent_a", message=msg1)
        await member._mailbox.send(to="agent_a", message=msg2)

        member._persist_inbox.return_value = [
            make_human_message("First"),
            make_human_message("Second"),
        ]

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        await hook.before_model(ctx, state, request)

        # _persist_inbox should be called with both messages
        member._persist_inbox.assert_called_once()
        call_args = member._persist_inbox.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0].content == "First"
        assert call_args[1].content == "Second"


# ---------------------------------------------------------------------------
# Test: Returns updated ModelRequest when messages are injected
# ---------------------------------------------------------------------------


class TestReturnUpdatedRequest:
    """Test that before_model returns an updated ModelRequest when messages are injected."""

    @pytest.mark.asyncio
    async def test_returns_updated_request_with_new_messages(self):
        """When messages are injected, returns request.override(messages=...)."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        # Queue a message
        msg = make_message(from_agent="agent_b", content="Hello")
        await member._mailbox.send(to="agent_a", message=msg)

        # Mock _persist_inbox
        persisted_msg = make_human_message("Hello")
        member._persist_inbox.return_value = [persisted_msg]

        ctx = make_ctx()
        state = make_state()
        request = make_request(messages=())

        result = await hook.before_model(ctx, state, request)

        # Result should be a ModelRequest (not None)
        assert result is not None
        assert isinstance(result, ModelRequest)
        # Result should have the new messages
        assert len(result.messages) == 1
        assert result.messages[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_returned_request_includes_all_state_messages(self):
        """Returned request includes all messages from state.messages_for_llm."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        # Start with existing messages in state
        existing_msg = make_human_message("Existing")
        state = make_state([existing_msg])

        # Queue a new message
        msg = make_message(from_agent="agent_b", content="New")
        await member._mailbox.send(to="agent_a", message=msg)

        new_msg = make_human_message("New")
        member._persist_inbox.return_value = [new_msg]

        ctx = make_ctx()
        request = make_request(messages=())

        result = await hook.before_model(ctx, state, request)

        # Result should include both existing and new messages
        assert result is not None
        assert len(result.messages) == 2
        assert result.messages[0].content == "Existing"
        assert result.messages[1].content == "New"

    @pytest.mark.asyncio
    async def test_returned_request_preserves_system_prompt(self):
        """Returned request preserves the original system_prompt."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        msg = make_message(from_agent="agent_b", content="Hello")
        await member._mailbox.send(to="agent_a", message=msg)

        member._persist_inbox.return_value = [make_human_message("Hello")]

        ctx = make_ctx()
        state = make_state()
        original_prompt = "Original system prompt"
        request = make_request(messages=())
        request = request.override(system_prompt=original_prompt)

        result = await hook.before_model(ctx, state, request)

        assert result is not None
        assert result.system_prompt == original_prompt


# ---------------------------------------------------------------------------
# Test: SSE events are emitted
# ---------------------------------------------------------------------------


class TestSSEEmission:
    """Test that SSE events are emitted correctly."""

    @pytest.mark.asyncio
    async def test_sse_event_emitted_when_should_emit_returns_true(self):
        """When _should_emit_inbox_sse returns True, _team._emit is called."""
        member = _mock_member("agent_a")
        member._should_emit_inbox_sse.return_value = True
        hook = TeamInboxHook(member)

        msg = make_message(from_agent="agent_b", content="Hello")
        await member._mailbox.send(to="agent_a", message=msg)

        persisted_msg = make_human_message("Hello")
        member._persist_inbox.return_value = [persisted_msg]

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        await hook.before_model(ctx, state, request)

        # _team._emit should be called
        member._team._emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sse_event_has_correct_args(self):
        """SSE event is emitted with correct agent, event, and extra fields."""
        member = _mock_member("agent_a")
        member._should_emit_inbox_sse.return_value = True
        hook = TeamInboxHook(member)

        msg = make_message(from_agent="agent_b", content="Test content")
        await member._mailbox.send(to="agent_a", message=msg)

        persisted_msg = make_human_message("Test content")
        member._persist_inbox.return_value = [persisted_msg]

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        await hook.before_model(ctx, state, request)

        # Verify _emit was called with correct args
        call_kwargs = member._team._emit.call_args[1]
        assert call_kwargs["agent"] == "agent_a"
        assert call_kwargs["event"] == "inbox"
        assert call_kwargs["extra"]["content"] == "Test content"
        assert call_kwargs["extra"]["from_agent"] == "agent_b"

    @pytest.mark.asyncio
    async def test_sse_event_not_emitted_when_should_emit_returns_false(self):
        """When _should_emit_inbox_sse returns False, _team._emit is not called."""
        member = _mock_member("agent_a")
        member._should_emit_inbox_sse.return_value = False
        hook = TeamInboxHook(member)

        msg = make_message(from_agent="agent_b", content="Hello")
        await member._mailbox.send(to="agent_a", message=msg)

        member._persist_inbox.return_value = [make_human_message("Hello")]

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        await hook.before_model(ctx, state, request)

        # _team._emit should not be called
        member._team._emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_sse_event_emitted_per_message(self):
        """Each message gets its own SSE event."""
        member = _mock_member("agent_a")
        member._should_emit_inbox_sse.return_value = True
        hook = TeamInboxHook(member)

        msg1 = make_message(from_agent="agent_b", content="First")
        msg2 = make_message(from_agent="agent_c", content="Second")

        await member._mailbox.send(to="agent_a", message=msg1)
        await member._mailbox.send(to="agent_a", message=msg2)

        member._persist_inbox.return_value = [
            make_human_message("First"),
            make_human_message("Second"),
        ]

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        await hook.before_model(ctx, state, request)

        # _team._emit should be called twice
        assert member._team._emit.call_count == 2

        # First call
        first_call = member._team._emit.call_args_list[0][1]
        assert first_call["extra"]["content"] == "First"
        assert first_call["extra"]["from_agent"] == "agent_b"

        # Second call
        second_call = member._team._emit.call_args_list[1][1]
        assert second_call["extra"]["content"] == "Second"
        assert second_call["extra"]["from_agent"] == "agent_c"

    @pytest.mark.asyncio
    async def test_sse_event_checks_should_emit_per_message(self):
        """_should_emit_inbox_sse is called per message with correct senders."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        msg1 = make_message(from_agent="agent_b", content="First")
        msg2 = make_message(from_agent="agent_c", content="Second")

        await member._mailbox.send(to="agent_a", message=msg1)
        await member._mailbox.send(to="agent_a", message=msg2)

        member._persist_inbox.return_value = [
            make_human_message("First"),
            make_human_message("Second"),
        ]

        # Mock to return True for first, False for second
        member._should_emit_inbox_sse.side_effect = [True, False]

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        await hook.before_model(ctx, state, request)

        # _should_emit_inbox_sse should be called twice
        assert member._should_emit_inbox_sse.call_count == 2

        # First call with agent_b
        assert member._should_emit_inbox_sse.call_args_list[0][0][0] == ["agent_b"]

        # Second call with agent_c
        assert member._should_emit_inbox_sse.call_args_list[1][0][0] == ["agent_c"]

        # _team._emit should only be called once (for the first message)
        member._team._emit.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_message_content(self):
        """Messages with empty content are still processed."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        msg = make_message(from_agent="agent_b", content="")
        await member._mailbox.send(to="agent_a", message=msg)

        member._persist_inbox.return_value = [make_human_message("")]

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        result = await hook.before_model(ctx, state, request)

        assert result is not None
        assert len(state.messages) == 1
        assert state.messages[0].content == ""

    @pytest.mark.asyncio
    async def test_very_long_message_content(self):
        """Messages with very long content are processed."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        long_content = "x" * 10000
        msg = make_message(from_agent="agent_b", content=long_content)
        await member._mailbox.send(to="agent_a", message=msg)

        member._persist_inbox.return_value = [make_human_message(long_content)]

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        result = await hook.before_model(ctx, state, request)

        assert result is not None
        assert len(state.messages) == 1
        assert state.messages[0].content == long_content

    @pytest.mark.asyncio
    async def test_special_characters_in_message(self):
        """Messages with special characters are processed."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        special_content = "Hello 🎉 \n\t\r special chars: @#$%^&*()"
        msg = make_message(from_agent="agent_b", content=special_content)
        await member._mailbox.send(to="agent_a", message=msg)

        member._persist_inbox.return_value = [make_human_message(special_content)]

        ctx = make_ctx()
        state = make_state()
        request = make_request()

        result = await hook.before_model(ctx, state, request)

        assert result is not None
        assert state.messages[0].content == special_content

    @pytest.mark.asyncio
    async def test_state_with_existing_messages_preserved(self):
        """Existing messages in state are preserved when new messages are added."""
        member = _mock_member("agent_a")
        hook = TeamInboxHook(member)

        existing1 = make_human_message("Existing 1")
        existing2 = make_human_message("Existing 2")
        state = make_state([existing1, existing2])

        msg = make_message(from_agent="agent_b", content="New")
        await member._mailbox.send(to="agent_a", message=msg)

        new_msg = make_human_message("New")
        member._persist_inbox.return_value = [new_msg]

        ctx = make_ctx()
        request = make_request()

        result = await hook.before_model(ctx, state, request)

        # All messages should be present
        assert len(state.messages) == 3
        assert state.messages[0].content == "Existing 1"
        assert state.messages[1].content == "Existing 2"
        assert state.messages[2].content == "New"

        # Result should also have all messages
        assert result is not None
        assert len(result.messages) == 3
