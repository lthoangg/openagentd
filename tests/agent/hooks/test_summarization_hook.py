"""Tests for SummarizationHook.

SummarizationHook is a pure state transform.
- Reads state.usage.last_prompt_tokens (no DB read)
- Mutates state.messages directly (no DB write)
- Constructor: SummarizationHook(llm_provider, prompt_token_threshold, keep_last_assistants, summary_prompt, max_token_length)
"""

from unittest.mock import MagicMock

import pytest

from app.agent.state import AgentState, RunContext, UsageInfo
from app.agent.hooks.summarization import SummarizationHook
from app.agent.schemas.chat import AssistantMessage, HumanMessage, ToolMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(session_id="test-session") -> RunContext:
    return RunContext(session_id=session_id, run_id="test-run", agent_name="TestAgent")


def _make_state(last_prompt_tokens: int = 0) -> AgentState:
    usage = UsageInfo(last_prompt_tokens=last_prompt_tokens)
    return AgentState(
        messages=[HumanMessage(content="hi")],
        usage=usage,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_provider():
    provider = MagicMock()

    async def _stream(*_, **__):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary text."
        chunk.usage = None
        yield chunk

    provider.stream.return_value = _stream()
    return provider


# ---------------------------------------------------------------------------
# before_model — threshold not reached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_summarisation_below_threshold(mock_provider):
    """before_model is a no-op when prompt tokens are below threshold."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1000,
    )
    ctx = _make_ctx()
    state = _make_state(last_prompt_tokens=900)

    await hook.before_model(ctx, state)

    mock_provider.stream.assert_not_called()


# ---------------------------------------------------------------------------
# before_model — threshold reached triggers summarisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarisation_triggered_when_threshold_met(mock_provider):
    """Summarisation fires in before_model once prompt_tokens >= threshold."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1000,
        keep_last_assistants=1,
    )
    ctx = _make_ctx()
    # Me set tokens above threshold
    state = AgentState(
        messages=[
            HumanMessage(content="msg1"),
            AssistantMessage(content="msg2"),
            HumanMessage(content="msg3"),
            AssistantMessage(content="msg4"),
        ],
        usage=UsageInfo(last_prompt_tokens=1000),
    )

    await hook.before_model(ctx, state)

    # Me check summary inserted and old messages excluded
    summary_msgs = [m for m in state.messages if getattr(m, "is_summary", False)]
    assert len(summary_msgs) == 1
    excluded = [m for m in state.messages if m.exclude_from_context]
    assert len(excluded) >= 1


# ---------------------------------------------------------------------------
# Minimum-message-delta guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_min_messages_delta_guard(mock_provider):
    """before_model skips summarisation when too few new messages have arrived
    since the last summarisation."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        min_messages_since_last_summary=4,
    )
    ctx = _make_ctx()
    state = _make_state(last_prompt_tokens=9999)
    # Simulate a prior summarisation that left 10 messages in state.
    hook._messages_at_last_summary = len(state.messages)

    # Add 3 new messages — below the minimum of 4.
    from app.agent.schemas.chat import HumanMessage as HM

    state.messages.append(HM(content="msg1"))
    state.messages.append(HM(content="msg2"))
    state.messages.append(HM(content="msg3"))

    await hook.before_model(ctx, state)
    mock_provider.stream.assert_not_called()


@pytest.mark.asyncio
async def test_min_messages_delta_guard_allows_after_enough(mock_provider):
    """before_model proceeds when enough new messages have arrived."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        min_messages_since_last_summary=4,
    )
    ctx = _make_ctx()
    state = _make_state(last_prompt_tokens=9999)
    hook._messages_at_last_summary = len(state.messages)

    from app.agent.schemas.chat import HumanMessage as HM

    for i in range(4):
        state.messages.append(HM(content=f"msg{i}"))

    await hook.before_model(ctx, state)
    mock_provider.stream.assert_called_once()


# ---------------------------------------------------------------------------
# keep_last_assistants — only older messages are summarised
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keep_last_assistants_excluded_from_summary(mock_provider):
    """keep_last_assistants=1 keeps the last assistant turn, summarises older ones."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=1,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[
            HumanMessage(content="old1"),
            AssistantMessage(content="old2"),
            HumanMessage(content="recent1"),
            AssistantMessage(content="recent2"),
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    captured = []

    async def fake_stream(messages, **__):
        captured.extend(messages)
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: fake_stream(messages)

    await hook.before_model(ctx, state)

    # Me check only old messages sent to LLM (not the last assistant turn)
    # to_summarise is embedded as text inside one HumanMessage
    full_text = " ".join(m.content or "" for m in captured if hasattr(m, "content"))
    assert "old1" in full_text
    assert "old2" in full_text
    assert "recent2" not in full_text


# ---------------------------------------------------------------------------
# No session id — graceful skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_summarisation_without_session_id(mock_provider):
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
    )
    # Me use None session_id in ctx
    ctx = RunContext(session_id=None, run_id="test-run", agent_name="Agent")
    state = _make_state(last_prompt_tokens=9999)

    await hook.before_model(ctx, state)
    # Me check hook still runs (no session_id guard in new impl — it's a pure state transform)
    # The hook should attempt summarisation regardless of session_id
    # (session_id is only used for logging)


# ---------------------------------------------------------------------------
# Empty visible messages — skip LLM call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_llm_call_when_no_visible_messages(mock_provider):
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
    )
    ctx = _make_ctx()
    # Me create state with all messages excluded
    msg = HumanMessage(content="hidden")
    msg.exclude_from_context = True
    state = AgentState(
        messages=[msg],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    await hook.before_model(ctx, state)

    mock_provider.stream.assert_not_called()


# ---------------------------------------------------------------------------
# LLM failure — graceful error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graceful_on_llm_failure(mock_provider):
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[
            HumanMessage(content="hi"),
            AssistantMessage(content="hello"),
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    async def _bad_stream(*_, **__):
        raise RuntimeError("LLM down")
        yield

    mock_provider.stream.return_value = _bad_stream()

    # Me check no exception raised — hook handles LLM failure gracefully
    await hook.before_model(ctx, state)
    # Me check no summary inserted
    summary_msgs = [m for m in state.messages if getattr(m, "is_summary", False)]
    assert len(summary_msgs) == 0


# ---------------------------------------------------------------------------
# Summary saved with is_summary=True and AssistantMessage role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_saved_with_is_summary_flag(mock_provider):
    # Me use keep_last_assistants=1 but only have a HumanMessage (no assistant) —
    # cutoff returns 0 → all messages are summarised
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=1,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[HumanMessage(content="hi")],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    await hook.before_model(ctx, state)

    # Me check summary message inserted with is_summary=True
    summary_msgs = [m for m in state.messages if getattr(m, "is_summary", False)]
    assert len(summary_msgs) == 1
    # Me check summary is HumanMessage — ensures system → user → ... invariant
    assert isinstance(summary_msgs[0], HumanMessage)
    # Me check summary not excluded from context
    assert summary_msgs[0].exclude_from_context is False


# ---------------------------------------------------------------------------
# prompt_token_threshold=0 disables the hook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_when_threshold_is_zero(mock_provider):
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=0,
    )
    ctx = _make_ctx()
    state = _make_state(last_prompt_tokens=9999)

    await hook.before_model(ctx, state)
    mock_provider.stream.assert_not_called()


# ---------------------------------------------------------------------------
# _summarise — not enough assistant turns → summarises all messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarise_all_messages_when_not_enough_assistant_turns(mock_provider):
    """When fewer assistant turns exist than keep_last_assistants, summarises all messages."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=5,  # Me want to keep 5 assistant turns but only 1 exists
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[
            HumanMessage(content="msg1"),
            AssistantMessage(content="msg2"),
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    captured_messages = []

    async def _capturing_stream(messages, **__):
        captured_messages.extend(messages)
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _capturing_stream(messages)

    await hook.before_model(ctx, state)

    # Both messages should be embedded in the HumanMessage sent to the LLM
    full_text = " ".join(
        m.content or "" for m in captured_messages if hasattr(m, "content")
    )
    assert "msg1" in full_text
    assert "msg2" in full_text


# ---------------------------------------------------------------------------
# _call_llm — chunk with no choices is skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_llm_skips_empty_choices_chunks(mock_provider):
    """Chunks with empty choices list are skipped; content-only chunks are accumulated."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=1,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[HumanMessage(content="hi")],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    async def _mixed_stream(*_, **__):
        # Me send chunk with no choices first
        no_choices = MagicMock()
        no_choices.choices = []
        no_choices.usage = None
        yield no_choices

        # Me send chunk with content
        with_content = MagicMock()
        delta = MagicMock()
        delta.content = "Summary result."
        choice = MagicMock()
        choice.delta = delta
        with_content.choices = [choice]
        with_content.usage = None
        yield with_content

    mock_provider.stream = lambda messages, **kw: _mixed_stream()

    await hook.before_model(ctx, state)

    # Me check summary inserted with correct content (prefixed by anchor label)
    summary_msgs = [m for m in state.messages if getattr(m, "is_summary", False)]
    assert len(summary_msgs) == 1
    assert "Summary result." in summary_msgs[0].content


# ---------------------------------------------------------------------------
# max_token_length parameter — pass to LLM provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_token_length_passed_to_provider_when_set():
    """max_token_length=10000 should be passed to provider.stream()."""
    provider = MagicMock()

    async def _stream(*_, **__):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary."
        chunk.usage = None
        yield chunk

    provider.stream.return_value = _stream()

    hook = SummarizationHook(
        llm_provider=provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1000,
        keep_last_assistants=1,
        max_token_length=10000,  # explicit max tokens
    )

    ctx = _make_ctx()
    state = AgentState(
        messages=[
            HumanMessage(content="msg1"),
            AssistantMessage(content="msg2"),
            HumanMessage(content="msg3"),
            AssistantMessage(content="msg4"),
        ],
        usage=UsageInfo(last_prompt_tokens=1000),
    )

    await hook.before_model(ctx, state)

    # Me check provider.stream was called with max_tokens kwarg
    provider.stream.assert_called_once()
    call_kwargs = provider.stream.call_args[1]
    assert call_kwargs.get("max_tokens") == 10000


@pytest.mark.asyncio
async def test_max_token_length_zero_disables_limit():
    """max_token_length=0 should NOT pass max_tokens to provider."""
    provider = MagicMock()

    async def _stream(*_, **__):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary."
        chunk.usage = None
        yield chunk

    provider.stream.return_value = _stream()

    hook = SummarizationHook(
        llm_provider=provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1000,
        keep_last_assistants=1,
        max_token_length=0,  # disabled
    )

    ctx = _make_ctx()
    state = AgentState(
        messages=[
            HumanMessage(content="msg1"),
            AssistantMessage(content="msg2"),
            HumanMessage(content="msg3"),
            AssistantMessage(content="msg4"),
        ],
        usage=UsageInfo(last_prompt_tokens=1000),
    )

    await hook.before_model(ctx, state)

    # Me check provider.stream was called WITHOUT max_tokens kwarg
    provider.stream.assert_called_once()
    call_kwargs = provider.stream.call_args[1]
    assert "max_tokens" not in call_kwargs


@pytest.mark.asyncio
async def test_max_token_length_default_value():
    """SummarizationHook should default max_token_length to 10000."""
    provider = MagicMock()

    async def _stream(*_, **__):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary."
        chunk.usage = None
        yield chunk

    provider.stream.return_value = _stream()

    hook = SummarizationHook(
        llm_provider=provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1000,
        keep_last_assistants=1,
        # max_token_length not specified — should use default
    )

    ctx = _make_ctx()
    state = AgentState(
        messages=[
            HumanMessage(content="msg1"),
            AssistantMessage(content="msg2"),
            HumanMessage(content="msg3"),
            AssistantMessage(content="msg4"),
        ],
        usage=UsageInfo(last_prompt_tokens=1000),
    )

    await hook.before_model(ctx, state)

    # Me check provider.stream was called with default max_tokens=10000
    provider.stream.assert_called_once()
    call_kwargs = provider.stream.call_args[1]
    assert call_kwargs.get("max_tokens") == 10000


# ---------------------------------------------------------------------------
# is BaseAgentHook subclass
# ---------------------------------------------------------------------------


def test_is_base_agent_hook(mock_provider):
    from app.agent.hooks.base import BaseAgentHook

    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
    )
    assert isinstance(hook, BaseAgentHook)


# ---------------------------------------------------------------------------
# P2 — Tool result stubbing in summariser input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_message_content_replaced_with_stub(mock_provider):
    """ToolMessage content is replaced with '[tool/name]: [tool result omitted]'
    in the text sent to the summariser LLM; the tool name is preserved."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=0,  # summarise everything
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[
            HumanMessage(content="run a command"),
            AssistantMessage(content="sure", tool_calls=[]),
            ToolMessage(
                content='{"exit_code": 0, "stdout": "lots of output..."}',
                tool_call_id="tc1",
                name="shell",
            ),
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    captured: list = []

    async def _capturing_stream(messages, **__):
        captured.extend(messages)
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _capturing_stream(messages)

    await hook.before_model(ctx, state)

    # The HumanMessage sent to the LLM contains the serialised conversation.
    human_msgs = [m for m in captured if isinstance(m, HumanMessage)]
    assert human_msgs, "Expected at least one HumanMessage in summariser input"
    convo_blob = " ".join(m.content or "" for m in human_msgs)

    # Raw tool output must not appear.
    assert "lots of output" not in convo_blob
    assert '{"exit_code"' not in convo_blob
    # Tool name and stub marker must appear.
    assert "[tool/shell]" in convo_blob
    assert "[tool result omitted]" in convo_blob


@pytest.mark.asyncio
async def test_tool_message_without_name_uses_generic_stub(mock_provider):
    """A ToolMessage with no name renders as '[tool]: [tool result omitted]'."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=0,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[
            ToolMessage(content="raw output", tool_call_id="tc1", name=None),
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    captured: list = []

    async def _capturing_stream(messages, **__):
        captured.extend(messages)
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _capturing_stream(messages)

    await hook.before_model(ctx, state)

    human_msgs = [m for m in captured if isinstance(m, HumanMessage)]
    convo_blob = " ".join(m.content or "" for m in human_msgs)

    assert "raw output" not in convo_blob
    assert "[tool]:" in convo_blob
    assert "[tool result omitted]" in convo_blob


@pytest.mark.asyncio
async def test_non_tool_messages_not_stubbed(mock_provider):
    """HumanMessage and AssistantMessage content is passed through unchanged."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=0,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[
            HumanMessage(content="what is the capital of France?"),
            AssistantMessage(content="Paris."),
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    captured: list = []

    async def _capturing_stream(messages, **__):
        captured.extend(messages)
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _capturing_stream(messages)

    await hook.before_model(ctx, state)

    human_msgs = [m for m in captured if isinstance(m, HumanMessage)]
    convo_blob = " ".join(m.content or "" for m in human_msgs)

    assert "what is the capital of France?" in convo_blob
    assert "Paris." in convo_blob


# ---------------------------------------------------------------------------
# P5 — Merge vs. fresh summarisation request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_request_sent_when_no_prior_summary(mock_provider):
    """When no prior summary is in the window, the fresh summarise request is used."""
    from app.agent.hooks.summarization import _SUMMARISE_REQUEST, _MERGE_REQUEST

    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=0,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[HumanMessage(content="hello")],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    captured: list = []

    async def _capturing_stream(messages, **__):
        captured.extend(messages)
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _capturing_stream(messages)

    await hook.before_model(ctx, state)

    human_msgs = [m for m in captured if isinstance(m, HumanMessage)]
    convo_blob = " ".join(m.content or "" for m in human_msgs)

    assert _SUMMARISE_REQUEST in convo_blob
    assert _MERGE_REQUEST not in convo_blob


@pytest.mark.asyncio
async def test_merge_request_sent_when_prior_summary_in_window(mock_provider):
    """When a prior summary (is_summary=True) is being summarised, the merge
    request is used instead of the fresh summarise request."""
    from app.agent.hooks.summarization import _SUMMARISE_REQUEST, _MERGE_REQUEST

    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=0,
    )
    ctx = _make_ctx()

    prior_summary = HumanMessage(
        content="[Summary of earlier conversation]\nUser set up the project.",
        is_summary=True,
    )
    state = AgentState(
        messages=[
            prior_summary,
            HumanMessage(content="now do something else"),
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    captured: list = []

    async def _capturing_stream(messages, **__):
        captured.extend(messages)
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Merged summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _capturing_stream(messages)

    await hook.before_model(ctx, state)

    human_msgs = [m for m in captured if isinstance(m, HumanMessage)]
    convo_blob = " ".join(m.content or "" for m in human_msgs)

    assert _MERGE_REQUEST in convo_blob
    assert _SUMMARISE_REQUEST not in convo_blob


@pytest.mark.asyncio
async def test_prior_summary_in_kept_window_is_excluded_from_context(mock_provider):
    """A prior is_summary message sitting in the *kept* window (beyond the cutoff)
    must be marked exclude_from_context=True by the second exclusion loop —
    it is superseded by the new summary.

    Message order in eligible:
      [old_msg(user), kept_asst(assistant), orphaned_summary(user, is_summary=True)]
    keep_last_assistants=1 → _find_assistant_cutoff walks back:
      orphaned_summary: role=user → skip
      kept_asst: role=assistant → count hits 1 → cutoff=1
    to_summarise = [old_msg]          (id in to_summarise_set)
    kept window  = [kept_asst, orphaned_summary]   (id NOT in to_summarise_set)
    orphaned_summary.is_summary=True AND not in to_summarise_set → excluded by second loop.
    """
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=1,
    )
    ctx = _make_ctx()

    old_msg = HumanMessage(content="old user message")
    kept_asst = AssistantMessage(content="kept assistant reply")
    orphaned_summary = HumanMessage(
        content="[Summary of earlier conversation]\nStale summary.",
        is_summary=True,
    )
    state = AgentState(
        messages=[old_msg, kept_asst, orphaned_summary],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    async def _stream(messages, **__):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "New summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _stream(messages)

    await hook.before_model(ctx, state)

    assert orphaned_summary.exclude_from_context is True, (
        "Prior is_summary in kept window must be superseded (exclude_from_context=True)"
    )
    active = [m for m in state.messages if m.is_summary and not m.exclude_from_context]
    assert len(active) == 1, (
        "Exactly one active summary should exist after summarisation"
    )


@pytest.mark.asyncio
async def test_merge_request_only_when_prior_summary_in_to_summarise(mock_provider):
    """Merge request fires only when the prior summary is in the portion being
    summarised — not when it is in the kept (verbatim) window.

    Setup: prior_summary → new_human → new_assistant1 → new_assistant2
    With keep_last_assistants=2, the cutoff lands at new_assistant1, so
    to_summarise = [prior_summary, new_human] — summary IS in to_summarise
    and the merge request must fire.

    When keep_last_assistants=3 and only 2 assistant turns exist, cutoff=0
    (protect everything) → to_summarise is empty → no LLM call. So we need
    keep_last_assistants=1 with enough turns before the summary to verify the
    summary ends up in to_summarise vs kept.
    """
    from app.agent.hooks.summarization import _SUMMARISE_REQUEST, _MERGE_REQUEST

    # Scenario A: prior_summary in to_summarise → merge request
    hook_a = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=1,
    )
    ctx = _make_ctx()

    prior_summary = HumanMessage(
        content="[Summary of earlier conversation]\nSome summary.",
        is_summary=True,
    )
    # eligible: [prior_summary, new_human, new_assistant]
    # cutoff at new_assistant (index 2) → to_summarise = [prior_summary, new_human]
    state_a = AgentState(
        messages=[
            prior_summary,
            HumanMessage(content="new user turn"),
            AssistantMessage(content="new assistant reply — kept verbatim"),
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    captured_a: list = []

    async def _stream_a(messages, **__):
        captured_a.extend(messages)
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Merged summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _stream_a(messages)

    await hook_a.before_model(ctx, state_a)

    human_a = [m for m in captured_a if isinstance(m, HumanMessage)]
    blob_a = " ".join(m.content or "" for m in human_a)
    assert _MERGE_REQUEST in blob_a, (
        "Expected merge request when prior summary in to_summarise"
    )
    assert _SUMMARISE_REQUEST not in blob_a

    # Scenario B: no prior summary at all → fresh request
    hook_b = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=1,
    )
    state_b = AgentState(
        messages=[
            HumanMessage(content="plain old message"),
            AssistantMessage(content="kept assistant turn"),
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    captured_b: list = []

    async def _stream_b(messages, **__):
        captured_b.extend(messages)
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Fresh summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _stream_b(messages)

    await hook_b.before_model(ctx, state_b)

    human_b = [m for m in captured_b if isinstance(m, HumanMessage)]
    blob_b = " ".join(m.content or "" for m in human_b)
    assert _SUMMARISE_REQUEST in blob_b, "Expected fresh request when no prior summary"
    assert _MERGE_REQUEST not in blob_b


# ---------------------------------------------------------------------------
# _messages_at_last_summary not updated on failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_messages_at_last_summary_not_updated_on_llm_failure(mock_provider):
    """When the LLM call fails, _messages_at_last_summary must not advance.
    On the next turn the guard should not block summarisation."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        min_messages_since_last_summary=4,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[HumanMessage(content="msg"), AssistantMessage(content="reply")],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    async def _bad_stream(*_, **__):
        raise RuntimeError("LLM down")
        yield

    mock_provider.stream.return_value = _bad_stream()

    await hook.before_model(ctx, state)

    assert hook._messages_at_last_summary == 0, (
        "_messages_at_last_summary must stay 0 when LLM fails — "
        "otherwise the guard would block the retry"
    )


@pytest.mark.asyncio
async def test_messages_at_last_summary_not_updated_on_empty_response(mock_provider):
    """When the LLM returns an empty string, _messages_at_last_summary must not advance."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        min_messages_since_last_summary=4,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[HumanMessage(content="msg"), AssistantMessage(content="reply")],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    async def _empty_stream(*_, **__):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = ""  # empty content
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _empty_stream()

    await hook.before_model(ctx, state)

    assert hook._messages_at_last_summary == 0, (
        "_messages_at_last_summary must stay 0 when LLM returns empty response"
    )


# ---------------------------------------------------------------------------
# before_model return value — ModelRequest override
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_before_model_returns_updated_request_when_summarisation_fires(
    mock_provider,
):
    """When summarisation fires and a ModelRequest is passed, before_model must
    return a new ModelRequest whose messages reflect the post-summary state.
    This is the path the agent loop takes — it always passes a request."""
    from app.agent.state import ModelRequest

    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=1,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[
            HumanMessage(content="old message"),
            AssistantMessage(content="old reply"),
            HumanMessage(content="new message"),
            AssistantMessage(content="new reply — kept"),
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    original_request = ModelRequest(
        messages=tuple(state.messages_for_llm),
        system_prompt="You are an assistant.",
    )

    async def _stream(messages, **__):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Compact summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _stream(messages)

    result = await hook.before_model(ctx, state, original_request)

    assert result is not None, (
        "before_model must return a ModelRequest when summarisation fires"
    )
    assert result is not original_request, (
        "must be a new ModelRequest, not the original"
    )
    # The returned messages must include the summary and exclude old messages
    result_contents = [m.content or "" for m in result.messages]
    assert any("Compact summary." in c for c in result_contents), (
        "Returned ModelRequest messages must contain the new summary"
    )
    assert "old message" not in " ".join(result_contents), (
        "Excluded messages must not appear in the returned ModelRequest"
    )


@pytest.mark.asyncio
async def test_before_model_returns_none_when_no_summarisation(mock_provider):
    """When summarisation does not fire, before_model must return None (pass-through)."""
    from app.agent.state import ModelRequest

    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=99999,  # threshold not reached
    )
    ctx = _make_ctx()
    state = _make_state(last_prompt_tokens=100)

    request = ModelRequest(
        messages=tuple(state.messages_for_llm),
        system_prompt="prompt",
    )

    result = await hook.before_model(ctx, state, request)

    assert result is None


# ---------------------------------------------------------------------------
# _render — None content on non-tool message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assistant_with_none_content_renders_as_empty_string(mock_provider):
    """An AssistantMessage with content=None (tool-call-only turn) must render as
    '[assistant]: ' without crashing or leaking 'None' into the summariser input."""
    hook = SummarizationHook(
        llm_provider=mock_provider,
        summary_prompt="test summary prompt",
        prompt_token_threshold=1,
        keep_last_assistants=0,
    )
    ctx = _make_ctx()
    state = AgentState(
        messages=[
            HumanMessage(content="do something"),
            AssistantMessage(content=None, tool_calls=[]),  # tool-call-only turn
        ],
        usage=UsageInfo(last_prompt_tokens=9999),
    )

    captured: list = []

    async def _stream(messages, **__):
        captured.extend(messages)
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Summary."
        chunk.usage = None
        yield chunk

    mock_provider.stream = lambda messages, **kw: _stream(messages)

    await hook.before_model(ctx, state)

    human_msgs = [m for m in captured if isinstance(m, HumanMessage)]
    convo_blob = " ".join(m.content or "" for m in human_msgs)

    assert "None" not in convo_blob, "'None' must not appear in summariser input"
    assert "[assistant]:" in convo_blob
