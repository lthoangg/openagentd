from uuid import UUID
from typing import Any, AsyncIterator

import pytest

from app.agent.agent_loop import Agent
from app.agent.providers.base import LLMProviderBase
from app.agent.schemas.agent import AgentContext, AgentStats
from app.agent.schemas.chat import AssistantMessage, ChatCompletionChunk, ChatMessage


class MockProvider(LLMProviderBase):
    """Minimal mock LLM provider for testing."""

    model = "mock-model"

    def __init__(self):
        super().__init__()

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> AssistantMessage:
        return AssistantMessage(content="mock")

    def stream(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatCompletionChunk]:
        async def _gen():
            yield ChatCompletionChunk(id="c", created=0, model="m", choices=[])

        return _gen()


_PROVIDER = MockProvider()


def test_agent_has_id_and_name():
    agent = Agent(llm_provider=_PROVIDER, name="researcher")
    assert agent.name == "researcher"
    assert isinstance(agent.id, UUID)


def test_agent_default_name():
    agent = Agent(llm_provider=_PROVIDER)
    assert agent.name == "Agent"


def test_agent_state_initialized():
    agent = Agent(llm_provider=_PROVIDER, name="test")
    assert agent.stats.agent_id == agent.id
    assert agent.stats.status == "idle"
    assert agent.stats.messages_count == 0
    assert agent.stats.total_tokens == 0


def test_agent_state_tracks_tokens():
    state = AgentStats(agent_id=Agent(llm_provider=_PROVIDER).id)
    assert state.total_tokens == 0
    state.total_tokens = 150
    assert state.total_tokens == 150


def test_agent_unique_ids():
    a1 = Agent(llm_provider=_PROVIDER, name="alpha")
    a2 = Agent(llm_provider=_PROVIDER, name="alpha")
    assert a1.id != a2.id


def test_assistant_message_has_agent_fields():
    from app.agent.schemas.chat import AssistantMessage

    agent = Agent(llm_provider=_PROVIDER, name="researcher")
    msg = AssistantMessage(
        content="hi",
        agent_id=str(agent.id),
        agent_name=agent.name,
    )
    assert msg.agent_id == str(agent.id)
    assert msg.agent_name == "researcher"


def test_agent_tools_registry_built():
    """Agent builds an internal tool dict from callables and Tool objects."""
    from app.agent.tools.registry import tool

    @tool
    def my_tool(x: int) -> int:
        """A simple tool."""
        return x * 2

    agent = Agent(llm_provider=_PROVIDER, name="tool-test", tools=[my_tool])
    assert len(agent._tools) == 1
    assert "my_tool" in agent._tools
    assert agent._tools["my_tool"].definition["function"]["name"] == "my_tool"


def test_agent_empty_tools():
    agent = Agent(llm_provider=_PROVIDER, name="no-tools")
    assert agent._tools == {}


# --- AgentContext / Generic[TContext] tests ---


def test_agent_context_defaults_to_none():
    agent = Agent(llm_provider=_PROVIDER)
    assert agent.context is None


def test_agent_context_base_class():
    ctx = AgentContext()
    assert isinstance(ctx, AgentContext)


def test_agent_accepts_typed_context():
    class UserContext(AgentContext):
        user_group: str = "default"
        user_id: int = 0

    ctx = UserContext(user_group="premium", user_id=42)
    agent = Agent(llm_provider=_PROVIDER, context=ctx)

    assert agent.context is ctx
    assert isinstance(agent.context, UserContext)
    assert agent.context.user_group == "premium"
    assert agent.context.user_id == 42


def test_agent_context_is_pydantic_validated():
    class StrictContext(AgentContext):
        score: int

    with pytest.raises(Exception):
        # score must be an int — passing a non-castable string should fail
        StrictContext(score="not-a-number")  # type: ignore


def test_agent_context_subclass_has_defaults():
    class LocaleContext(AgentContext):
        locale: str = "en"
        timezone: str = "UTC"

    agent = Agent(llm_provider=_PROVIDER, context=LocaleContext())
    assert agent.context is not None
    assert agent.context.locale == "en"
    assert agent.context.timezone == "UTC"
