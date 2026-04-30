"""Tests for app/hooks/session_log.py — SessionLogHook."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.agent.state import AgentState, RunContext
from app.agent.hooks.session_log import SessionLogHook, _truncate
from app.agent.schemas.chat import HumanMessage


# ---------------------------------------------------------------------------
# _truncate helper
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_none_returns_none(self):
        assert _truncate(None) is None

    def test_short_text_unchanged(self):
        assert _truncate("hello", max_len=100) == "hello"

    def test_long_text_truncated(self):
        text = "a" * 200
        result = _truncate(text, max_len=50)
        assert result is not None
        assert len(result) < 200
        assert result.startswith("a" * 50)
        assert "+150]" in result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    messages=None,
    tool_names=None,
    total_tokens=0,
) -> AgentState:
    return AgentState(
        messages=messages or [],
        tool_names=tool_names or [],
        metadata={
            "total_tokens": total_tokens,
        },
    )


def _make_ctx(session_id="test-sess", agent_name="leader") -> RunContext:
    return RunContext(session_id=session_id, run_id="test-run", agent_name=agent_name)


# ---------------------------------------------------------------------------
# SessionLogHook
# ---------------------------------------------------------------------------


class TestSessionLogHook:
    def test_construction(self, tmp_path):
        hook = SessionLogHook(session_id="sess1", agent_name="bot")
        assert hook._session_id == "sess1"
        assert hook._agent_name == "bot"

    async def test_before_agent_logs_trigger(self, tmp_path):
        hook = SessionLogHook(session_id="test-sess", agent_name="leader")
        ctx = _make_ctx()
        state = _make_state(
            messages=[HumanMessage(content="Hello!")],
            tool_names=["web_search"],
        )

        with patch.object(hook, "_write") as mock_write:
            await hook.before_agent(ctx, state)
            mock_write.assert_called_once()
            call_args = mock_write.call_args
            assert call_args[0][0] == "agent_start"
            assert call_args[1]["trigger"] == "Hello!"
            assert call_args[1]["context_messages"] == 1
            assert call_args[1]["tools"] == ["web_search"]

    async def test_after_agent_logs_with_elapsed(self, tmp_path):
        from app.agent.schemas.chat import AssistantMessage

        hook = SessionLogHook(session_id="test-sess", agent_name="leader")
        ctx = _make_ctx()
        hook._run_start = 100.0  # fake start time
        hook._iteration = 3
        state = _make_state(total_tokens=1500)

        with patch.object(hook, "_write") as mock_write:
            msg = AssistantMessage(content="Final answer here.")
            with patch("app.agent.hooks.session_log.time") as mock_time:
                mock_time.monotonic.return_value = 102.5  # 2.5s elapsed
                await hook.after_agent(ctx, state, msg)
            mock_write.assert_called_once()
            args = mock_write.call_args
            assert args[0][0] == "agent_done"
            assert args[1]["content"] == "Final answer here."
            assert args[1]["elapsed_seconds"] == 2.5
            assert args[1]["iterations"] == 3
            assert args[1]["total_tokens"] == 1500

    async def test_before_model_logs_with_role_distribution(self):
        from app.agent.schemas.chat import HumanMessage, SystemMessage

        hook = SessionLogHook(session_id="s1", agent_name="bot")
        ctx = _make_ctx("s1", "bot")
        state = _make_state(
            messages=[
                SystemMessage(content="sys"),
                HumanMessage(content="hi"),
                HumanMessage(content="again"),
            ]
        )
        with patch.object(hook, "_write") as mock_write:
            await hook.before_model(ctx, state)
            mock_write.assert_called_once()
            args = mock_write.call_args
            assert args[0][0] == "model_call"
            assert args[1]["context_messages"] == 3
            assert args[1]["iteration"] == 1
            assert args[1]["role_distribution"] == {"system": 1, "user": 2}

    async def test_after_model_with_content(self):
        from app.agent.schemas.chat import AssistantMessage

        hook = SessionLogHook(session_id="s1", agent_name="bot")
        ctx = _make_ctx("s1", "bot")
        state = _make_state()
        with patch.object(hook, "_write") as mock_write:
            msg = AssistantMessage(content="response text")
            await hook.after_model(ctx, state, msg)
            mock_write.assert_called_once()
            args = mock_write.call_args
            assert args[0][0] == "assistant_message"
            assert args[1]["content"] == "response text"
            assert args[1]["has_tool_calls"] is False
            assert args[1]["tool_call_count"] == 0

    async def test_after_model_with_tool_calls(self):
        from app.agent.schemas.chat import AssistantMessage, FunctionCall, ToolCall

        hook = SessionLogHook(session_id="s1", agent_name="bot")
        ctx = _make_ctx("s1", "bot")
        state = _make_state()
        tc = ToolCall(
            id="tc1",
            function=FunctionCall(name="web_search", arguments='{"q": "x"}'),
        )

        with patch.object(hook, "_write") as mock_write:
            msg = AssistantMessage(content="Let me search", tool_calls=[tc])
            await hook.after_model(ctx, state, msg)
            args = mock_write.call_args
            assert args[1]["has_tool_calls"] is True
            assert args[1]["tool_call_count"] == 1
            assert args[1]["tool_names"] == ["web_search"]

    async def test_on_model_delta_logs_usage(self):
        hook = SessionLogHook(session_id="s1", agent_name="bot")
        ctx = _make_ctx("s1", "bot")
        state = _make_state()
        chunk = MagicMock()
        chunk.usage.prompt_tokens = 100
        chunk.usage.completion_tokens = 50
        chunk.usage.total_tokens = 150
        chunk.usage.cached_tokens = 20
        chunk.usage.thoughts_tokens = 10
        chunk.usage.tool_use_tokens = None
        chunk.model = "gemini-pro"

        with patch.object(hook, "_write") as mock_write:
            await hook.on_model_delta(ctx, state, chunk)
            mock_write.assert_called_once()
            args = mock_write.call_args
            assert args[0][0] == "usage"
            assert args[1]["prompt_tokens"] == 100
            assert args[1]["model"] == "gemini-pro"

    async def test_on_model_delta_no_usage_skipped(self):
        hook = SessionLogHook(session_id="s1", agent_name="bot")
        ctx = _make_ctx("s1", "bot")
        state = _make_state()
        chunk = MagicMock()
        chunk.usage = None

        with patch.object(hook, "_write") as mock_write:
            await hook.on_model_delta(ctx, state, chunk)
            mock_write.assert_not_called()

    def test_ensure_dir_creates_directory(self, tmp_path):
        """_ensure_dir creates the log directory on first call."""
        log_dir = tmp_path / "new_subdir" / "logs"
        hook = SessionLogHook(session_id="s1", agent_name="bot")
        hook._log_dir = log_dir  # override to tmp path
        hook._path = log_dir / "bot.jsonl"
        assert not log_dir.exists()
        hook._ensure_dir()
        assert log_dir.exists()
        assert hook._path_created is True

    def test_ensure_dir_only_called_once(self, tmp_path):
        """_ensure_dir sets _path_created=True so subsequent calls skip mkdir."""
        log_dir = tmp_path / "logs"
        hook = SessionLogHook(session_id="s1", agent_name="bot")
        hook._log_dir = log_dir
        hook._path = log_dir / "bot.jsonl"
        hook._ensure_dir()
        hook._ensure_dir()  # second call — should not raise
        assert hook._path_created is True

    def test_write_oserror_handled(self, tmp_path):
        """OSError during file write should not raise (session_log.py:107-112).

        We need the open() to succeed but the write() to fail, so that line 107
        (fh.write(...)) is executed and then the OSError is caught.
        """
        hook = SessionLogHook(session_id="s1", agent_name="bot")
        hook._path_created = True

        # Mock a file handle whose write() raises OSError
        mock_fh = MagicMock()
        mock_fh.__enter__ = MagicMock(return_value=mock_fh)
        mock_fh.__exit__ = MagicMock(return_value=False)
        mock_fh.write = MagicMock(side_effect=OSError("disk full"))

        with patch("pathlib.Path.open", return_value=mock_fh):
            # Should not raise — OSError is swallowed and logged
            hook._write("test_event", foo="bar")

        # Confirm write was attempted
        mock_fh.write.assert_called_once()
