"""Tests for app/agent/hooks/streaming.py — StreamingHook."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.agent.state import AgentState, RunContext
from app.agent.hooks.streaming import (
    StreamingHook,
    ToolStartSignal,
    ToolEndSignal,
)
from app.agent.schemas.chat import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionDelta,
    FunctionCall,
    HumanMessage,
    ToolCall,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_chunk(text: str = "hi") -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id="c1",
        created=1_000_000,
        model="mock",
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionDelta(content=text),
                finish_reason="stop",
            )
        ],
    )


def _make_tool_call() -> ToolCall:
    return ToolCall(id="call_1", function=FunctionCall(name="greet", arguments="{}"))


def _make_state() -> AgentState:
    return AgentState(messages=[HumanMessage(content="hi")])


def _make_ctx(name: str = "bot") -> RunContext:
    return RunContext(session_id="test-session", run_id="test-run", agent_name=name)


# ── StreamingHook ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_hook_on_model_delta_queues_chunk():
    hook = StreamingHook()
    chunk = _make_chunk("hello")
    ctx = _make_ctx()
    state = _make_state()

    await hook.on_model_delta(ctx, state, chunk)
    item = await asyncio.wait_for(hook._queue.get(), timeout=1.0)
    assert item is chunk


@pytest.mark.asyncio
async def test_streaming_hook_after_tool_call_queues_signal():
    """wrap_tool_call enqueues ToolStartSignal before and ToolEndSignal after."""
    hook = StreamingHook()
    ctx = _make_ctx("mybot")
    state = _make_state()
    tc = _make_tool_call()
    handler = AsyncMock(return_value="result")

    returned = await hook.wrap_tool_call(ctx, state, tc, handler)
    assert returned == "result"

    start = await asyncio.wait_for(hook._queue.get(), timeout=1.0)
    assert isinstance(start, ToolStartSignal)
    assert start.agent_name == "mybot"
    assert start.tool_call is tc

    end = await asyncio.wait_for(hook._queue.get(), timeout=1.0)
    assert isinstance(end, ToolEndSignal)
    assert end.agent_name == "mybot"
    assert end.tool_call is tc


@pytest.mark.asyncio
async def test_streaming_hook_after_agent_queues_sentinel():
    hook = StreamingHook()
    ctx = _make_ctx()
    state = _make_state()
    msg = AssistantMessage(content="done")

    await hook.after_agent(ctx, state, msg)
    # The sentinel is internal; consuming via __anext__ raises StopAsyncIteration
    with pytest.raises(StopAsyncIteration):
        await hook.__anext__()


@pytest.mark.asyncio
async def test_streaming_hook_signal_done():
    hook = StreamingHook()
    hook.signal_done()
    with pytest.raises(StopAsyncIteration):
        await hook.__anext__()


@pytest.mark.asyncio
async def test_streaming_hook_aiter_yields_chunks_then_stops():
    hook = StreamingHook()
    chunks = [_make_chunk(f"msg{i}") for i in range(3)]

    async def _fill():
        ctx = _make_ctx()
        for c in chunks:
            await hook.on_model_delta(ctx, _make_state(), c)
        await hook.after_agent(ctx, _make_state(), AssistantMessage(content=""))

    asyncio.create_task(_fill())

    received = []
    async for item in hook:
        received.append(item)

    assert received == chunks


@pytest.mark.asyncio
async def test_streaming_hook_aiter_returns_self():
    hook = StreamingHook()
    assert hook.__aiter__() is hook


@pytest.mark.asyncio
async def test_streaming_hook_queue_property_exposed():
    hook = StreamingHook()
    assert hook.queue is hook._queue


@pytest.mark.asyncio
async def test_streaming_hook_custom_maxsize():
    hook = StreamingHook(maxsize=4)
    assert hook._queue.maxsize == 4


@pytest.mark.asyncio
async def test_streaming_hook_on_rate_limit_enqueues_signal():
    """on_rate_limit enqueues a RateLimitSignal with correct fields."""
    from app.agent.hooks.streaming import RateLimitSignal

    hook = StreamingHook()
    ctx = _make_ctx()
    state = _make_state()

    await hook.on_rate_limit(ctx, state, retry_after=30, attempt=2, max_attempts=5)
    item = await asyncio.wait_for(hook._queue.get(), timeout=1.0)
    assert isinstance(item, RateLimitSignal)
    assert item.retry_after == 30
    assert item.attempt == 2
    assert item.max_attempts == 5
