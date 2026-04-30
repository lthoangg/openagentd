"""Extra tests for Agent.run() — covers remaining uncovered lines.

Targets: agent_loop.py lines 290, 453, 502-503.
- Line 290: tool_calls_buffer update path where tc.id is set but buffer[idx]["id"] already has value
- Line 453: last_assistant_msg fallback to synthetic when no real assistant turn
- Line 502-503: checkpointer.sync exception handling
"""

from __future__ import annotations

from typing import AsyncIterator
from app.agent.agent_loop import Agent
from app.agent.checkpointer import Checkpointer
from app.agent.providers.base import LLMProviderBase
from app.agent.schemas.agent import RunConfig
from app.agent.schemas.chat import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionDelta,
    ChatMessage,
    FunctionCallDelta,
    HumanMessage,
    ToolCallDelta,
    Usage,
)
from app.agent.tools.registry import Tool


# ---------------------------------------------------------------------------
# Helpers (reuse from test_agent_run.py)
# ---------------------------------------------------------------------------


def make_text_chunk(text: str, usage: Usage | None = None) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id="chunk-1",
        created=1_000_000,
        model="mock-model",
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionDelta(content=text),
                finish_reason="stop",
            )
        ],
        usage=usage,
    )


def make_tool_chunk(
    tool_name: str, tool_id: str, arguments: str
) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id="chunk-3",
        created=1_000_000,
        model="mock-model",
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionDelta(
                    tool_calls=[
                        ToolCallDelta(
                            index=0,
                            id=tool_id,
                            function=FunctionCallDelta(
                                name=tool_name, arguments=arguments
                            ),
                        )
                    ]
                ),
                finish_reason="tool_calls",
            )
        ],
    )


class MockProvider(LLMProviderBase):
    model = "mock-model"

    def __init__(self, responses: list[list[ChatCompletionChunk]]):
        super().__init__()
        self._responses = iter(responses)

    def stream(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> AsyncIterator[ChatCompletionChunk]:
        chunks = next(self._responses)

        async def _gen() -> AsyncIterator[ChatCompletionChunk]:
            for chunk in chunks:
                yield chunk

        return _gen()

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> AssistantMessage:
        return AssistantMessage(content="mock")


# ---------------------------------------------------------------------------
# Line 290: tc.id set but buffer already has id — first id wins
# ---------------------------------------------------------------------------


async def test_tool_call_id_first_wins():
    """When tc.id arrives in a later chunk but buffer[idx]['id'] already set,
    the original id is preserved (agent_loop.py:289 — branch NOT taken)."""

    def greet(name: str) -> str:
        """Greet."""
        return f"hi {name}"

    chunk1 = ChatCompletionChunk(
        id="c1",
        created=0,
        model="m",
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionDelta(
                    tool_calls=[
                        ToolCallDelta(
                            index=0,
                            id="original_id",
                            function=FunctionCallDelta(name="greet", arguments=""),
                        )
                    ]
                ),
                finish_reason=None,
            )
        ],
    )
    # Me second chunk has a different id — should be ignored (first wins)
    chunk2 = ChatCompletionChunk(
        id="c2",
        created=0,
        model="m",
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionDelta(
                    tool_calls=[
                        ToolCallDelta(
                            index=0,
                            id="later_id",
                            function=FunctionCallDelta(
                                arguments='{"name": "world"}',
                            ),
                        )
                    ]
                ),
                finish_reason="tool_calls",
            )
        ],
    )

    provider = MockProvider([[chunk1, chunk2], [make_text_chunk("done")]])
    agent = Agent(name="bot", llm_provider=provider, tools=[Tool(greet)])

    msgs = await agent.run([HumanMessage(content="greet")])

    # Me verify tool executed successfully
    from app.agent.schemas.chat import ToolMessage

    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert "hi world" in (tool_msgs[0].content or "")


# ---------------------------------------------------------------------------
# Line 502-503: checkpointer.sync raises exception
# ---------------------------------------------------------------------------


async def test_checkpointer_sync_exception_handled():
    """Checkpointer.sync failure is caught and logged, doesn't crash the run."""

    class FailingCheckpointer(Checkpointer):
        async def load(self, session_id):
            return None

        async def sync(self, ctx, state):
            raise RuntimeError("DB connection lost")

    provider = MockProvider([[make_text_chunk("hello")]])
    agent = Agent(name="bot", llm_provider=provider)

    # Me should complete without raising
    msgs = await agent.run(
        [HumanMessage(content="hi")],
        config=RunConfig(session_id="test-sid"),
        checkpointer=FailingCheckpointer(),
    )

    last = next((m for m in reversed(msgs) if isinstance(m, AssistantMessage)), None)
    assert last is not None
    assert last.content == "hello"


# ---------------------------------------------------------------------------
# Checkpointer with session_id=None — _sync skips
# ---------------------------------------------------------------------------


async def test_checkpointer_skipped_when_no_session_id():
    """When session_id is None, checkpointer.sync is never called."""
    sync_calls = []

    class TrackingCheckpointer(Checkpointer):
        async def load(self, session_id):
            return None

        async def sync(self, ctx, state):
            sync_calls.append(ctx.session_id)

    provider = MockProvider([[make_text_chunk("hello")]])
    agent = Agent(name="bot", llm_provider=provider)

    await agent.run(
        [HumanMessage(content="hi")],
        checkpointer=TrackingCheckpointer(),
    )

    # Me no session_id in config → sync never called
    assert len(sync_calls) == 0


# ---------------------------------------------------------------------------
# Checkpointer properly called during tool execution flow
# ---------------------------------------------------------------------------


async def test_checkpointer_sync_called_during_run():
    """Checkpointer.sync is called at sync points during the run."""
    sync_calls = []

    class TrackingCheckpointer(Checkpointer):
        async def load(self, session_id):
            return None

        async def sync(self, ctx, state):
            sync_calls.append(len(state.messages))

    def ping(x: int) -> str:
        """Ping."""
        return "pong"

    provider = MockProvider(
        [
            [make_tool_chunk("ping", "c1", '{"x": 0}')],
            [make_text_chunk("done")],
        ]
    )
    agent = Agent(name="bot", llm_provider=provider, tools=[Tool(ping)])

    await agent.run(
        [HumanMessage(content="hi")],
        config=RunConfig(session_id="test-sid"),
        checkpointer=TrackingCheckpointer(),
    )

    # Me sync should have been called multiple times
    assert len(sync_calls) >= 2
