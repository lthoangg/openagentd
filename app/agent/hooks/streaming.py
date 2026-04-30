"""StreamingHook — push model deltas into an asyncio.Queue for SSE consumption."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.agent.hooks.base import BaseAgentHook
from app.agent.schemas.chat import AssistantMessage, ChatCompletionChunk, ToolCall

if TYPE_CHECKING:
    from app.agent.state import AgentState, RunContext, ToolCallHandler


class _Sentinel:
    """End-of-stream marker placed in the queue by signal_done()."""


_SENTINEL = _Sentinel()  # signals end-of-stream


@dataclass
class ToolStartSignal:
    """Queued just before a tool begins executing — full args available."""

    agent_name: str
    tool_call: ToolCall


@dataclass
class ToolEndSignal:
    """Queued when a tool has finished executing."""

    agent_name: str
    tool_call: ToolCall
    result: str | None = None


@dataclass
class RateLimitSignal:
    """Queued when the provider returns 429 Too Many Requests."""

    retry_after: int  # seconds until quota resets (0 if unknown)
    attempt: int  # 1-based attempt number that just failed
    max_attempts: int


# Union type for queue items (includes sentinel for end-of-stream signalling)
StreamQueueItem = (
    ChatCompletionChunk | ToolStartSignal | ToolEndSignal | RateLimitSignal | _Sentinel
)


class StreamingHook(BaseAgentHook):
    """Captures on_model_delta chunks and queues them for SSE streaming.

    Usage::

        mw = StreamingHook()
        agent = Agent(..., hooks=[mw, ...])

        # Start the agent in the background
        asyncio.create_task(agent.run(messages, config=config))

        # Consume chunks
        async for chunk in mw:
            yield chunk
    """

    def __init__(self, maxsize: int = 256) -> None:
        # Typed as Any so tests can inject arbitrary sentinel/bad-chunk objects.
        # The public __anext__ return type is still narrowly declared.
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=maxsize)

    @property
    def queue(self) -> asyncio.Queue:
        """Expose the underlying queue."""
        return self._queue

    async def on_model_delta(
        self, ctx: "RunContext", state: "AgentState", chunk: ChatCompletionChunk
    ) -> None:
        await self._queue.put(chunk)
        # Yield to the SSE consumer so each chunk is sent before the next arrives.
        await asyncio.sleep(0)

    async def on_rate_limit(
        self,
        ctx: "RunContext",
        state: "AgentState",
        retry_after: int,
        attempt: int,
        max_attempts: int,
    ) -> None:
        await self._queue.put(
            RateLimitSignal(
                retry_after=retry_after,
                attempt=attempt,
                max_attempts=max_attempts,
            )
        )
        await asyncio.sleep(0)

    async def wrap_tool_call(
        self,
        ctx: "RunContext",
        state: "AgentState",
        tool_call: ToolCall,
        handler: "ToolCallHandler",
    ) -> str:
        """Signal tool start (full args), execute, then signal completion."""
        await self._queue.put(
            ToolStartSignal(agent_name=ctx.agent_name, tool_call=tool_call)
        )
        await asyncio.sleep(0)
        result = await handler(ctx, state, tool_call)
        await self._queue.put(
            ToolEndSignal(agent_name=ctx.agent_name, tool_call=tool_call, result=result)
        )
        await asyncio.sleep(0)
        return result

    async def after_agent(
        self, ctx: "RunContext", state: "AgentState", response: AssistantMessage
    ) -> None:
        """Signal end of stream after the full agent loop completes."""
        await self._queue.put(_SENTINEL)

    def signal_done(self) -> None:
        """Manually signal end-of-stream (e.g. on error)."""
        self._queue.put_nowait(_SENTINEL)

    def __aiter__(self):
        return self

    async def __anext__(
        self,
    ) -> ChatCompletionChunk | ToolStartSignal | ToolEndSignal | RateLimitSignal:
        item = await self._queue.get()
        if isinstance(item, _Sentinel):
            raise StopAsyncIteration
        return item
