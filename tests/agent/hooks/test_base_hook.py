"""Tests for BaseAgentHook — ensures all no-op methods are callable."""

from unittest.mock import MagicMock

from app.agent.state import AgentState, ModelRequest, RunContext
from app.agent.hooks.base import BaseAgentHook
from app.agent.schemas.chat import (
    AssistantMessage,
    ChatCompletionChunk,
    HumanMessage,
)


def _make_state() -> AgentState:
    return AgentState(messages=[HumanMessage(content="hi")])


def _make_ctx() -> RunContext:
    return RunContext(session_id="test-session", run_id="test-run", agent_name="bot")


async def test_base_hook_all_methods_are_no_ops():
    """Every BaseAgentHook method can be awaited without error."""
    hook = BaseAgentHook()
    ctx = _make_ctx()
    state = _make_state()
    assistant = AssistantMessage(content="hi")
    chunk = MagicMock(spec=ChatCompletionChunk)
    request = ModelRequest(messages=tuple(state.messages), system_prompt="hi")

    await hook.on_start()
    await hook.on_end()
    await hook.before_agent(ctx, state)
    await hook.after_agent(ctx, state, assistant)
    result = await hook.before_model(ctx, state, request)
    assert result is None  # pass-through returns None
    await hook.on_model_delta(ctx, state, chunk)
    await hook.after_model(ctx, state, assistant)


async def test_base_hook_on_rate_limit_is_no_op():
    """on_rate_limit is a no-op pass that completes without error."""
    hook = BaseAgentHook()
    ctx = _make_ctx()
    state = _make_state()
    # Should return None without raising
    result = await hook.on_rate_limit(
        ctx, state, retry_after=5, attempt=1, max_attempts=3
    )
    assert result is None


def test_base_hook_is_instance():
    """BaseAgentHook can be instantiated and is its own type."""
    hook = BaseAgentHook()
    assert isinstance(hook, BaseAgentHook)
