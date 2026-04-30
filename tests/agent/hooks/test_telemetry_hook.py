"""Tests for app/agent/hooks/telemetry.py — TelemetryHook."""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, patch
from uuid import UUID


from app.agent.hooks.telemetry import TelemetryHook
from app.agent.schemas.chat import (
    AssistantMessage,
    HumanMessage,
    SystemMessage,
)
from app.agent.state import AgentState, ModelRequest, RunContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ctx(
    agent_name: str = "bot",
    session_id: str | None = "sess_1",
    run_id: str = "run_1",
) -> RunContext:
    return RunContext(session_id=session_id, run_id=run_id, agent_name=agent_name)


def make_state(messages=None, system_prompt: str = "You are helpful.") -> AgentState:
    return AgentState(messages=messages or [], system_prompt=system_prompt)


async def _call_wrap(hook: TelemetryHook, prompt: str) -> str:
    """Helper: call wrap_model_call and return the captured system prompt."""
    ctx = make_ctx()
    state = make_state(system_prompt=prompt)
    request = ModelRequest(messages=(), system_prompt=prompt)
    received = []

    async def handler(req: ModelRequest) -> AssistantMessage:
        received.append(req.system_prompt)
        return AssistantMessage(content="ok")

    await hook.wrap_model_call(ctx, state, request, handler)
    return received[0]


# ---------------------------------------------------------------------------
# wrap_model_call — captures system prompt
# ---------------------------------------------------------------------------


class TestWrapModelCall:
    async def test_captures_system_prompt(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        await _call_wrap(hook, "My system prompt")
        assert hook._last_system_prompt == "My system prompt"

    async def test_calls_handler(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx()
        state = make_state()
        request = ModelRequest(messages=(), system_prompt="prompt")
        handler = AsyncMock(return_value=AssistantMessage(content="response"))

        result = await hook.wrap_model_call(ctx, state, request, handler)

        handler.assert_awaited_once_with(request)
        assert result.content == "response"

    async def test_returns_handler_result(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx()
        state = make_state()
        request = ModelRequest(messages=(), system_prompt="p")
        expected = AssistantMessage(content="expected response")
        handler = AsyncMock(return_value=expected)

        result = await hook.wrap_model_call(ctx, state, request, handler)
        assert result is expected


# ---------------------------------------------------------------------------
# after_agent — writes JSONL file
# ---------------------------------------------------------------------------


class TestAfterAgent:
    async def test_creates_directory(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id="sess_abc")
        state = make_state()
        hook._last_system_prompt = "sys"

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        assert (tmp_path / "sess_abc").is_dir()

    async def test_writes_jsonl_file(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id="sess_1", run_id="run_1")
        state = make_state(messages=[HumanMessage(content="hello")])
        hook._last_system_prompt = "sys prompt"

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        files = list((tmp_path / "sess_1").iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".jsonl"

    async def test_line_0_is_system_prompt(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id="s1", run_id="r1")
        state = make_state(messages=[HumanMessage(content="hi")])
        hook._last_system_prompt = "captured prompt"

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        out_file = next((tmp_path / "s1").iterdir())
        lines = out_file.read_text().strip().split("\n")
        first = json.loads(lines[0])
        assert first["type"] == "system"
        assert first["content"] == "captured prompt"

    async def test_lines_1_n_are_messages(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id="s2", run_id="r2")
        state = make_state(
            messages=[
                HumanMessage(content="hello"),
                AssistantMessage(content="world"),
            ]
        )
        hook._last_system_prompt = "sys"

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        out_file = next((tmp_path / "s2").iterdir())
        lines = out_file.read_text().strip().split("\n")
        # Me line 0 = system, lines 1+ = messages
        assert len(lines) == 3
        msg1 = json.loads(lines[1])
        assert msg1["role"] == "user"
        assert msg1["content"] == "hello"

    async def test_system_messages_excluded_from_lines(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id="s3", run_id="r3")
        state = make_state(
            messages=[
                SystemMessage(content="sys in messages"),
                HumanMessage(content="hi"),
            ]
        )
        hook._last_system_prompt = "sys"

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        out_file = next((tmp_path / "s3").iterdir())
        lines = out_file.read_text().strip().split("\n")
        # Me only line 0 (system) + line 1 (human) — SystemMessage excluded
        assert len(lines) == 2
        msg = json.loads(lines[1])
        assert msg["role"] == "user"

    async def test_user_msg_id_uses_human_db_id(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id="s4", run_id="run_fallback")
        human = HumanMessage(content="hi")
        human.db_id = UUID("12345678-1234-5678-1234-567812345678")
        state = make_state(messages=[human])
        hook._last_system_prompt = "sys"

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        files = list((tmp_path / "s4").iterdir())
        assert files[0].stem == "12345678-1234-5678-1234-567812345678"

    async def test_user_msg_id_falls_back_to_run_id(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id="s5", run_id="my_run_id")
        state = make_state(messages=[HumanMessage(content="hi")])
        hook._last_system_prompt = "sys"

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        files = list((tmp_path / "s5").iterdir())
        assert files[0].stem == "my_run_id"

    async def test_user_msg_id_skips_is_summary_messages(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id="s6", run_id="run_skip_summary")
        summary_msg = HumanMessage(content="[summary]")
        summary_msg.is_summary = True
        summary_msg.db_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        real_msg = HumanMessage(content="real question")
        # Me no db_id on real_msg → falls back to run_id
        state = make_state(messages=[summary_msg, real_msg])
        hook._last_system_prompt = "sys"

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        files = list((tmp_path / "s6").iterdir())
        # Me summary skipped → run_id used
        assert files[0].stem == "run_skip_summary"

    async def test_session_id_none_uses_no_session_dir(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id=None, run_id="r_no_sess")
        state = make_state()
        hook._last_system_prompt = "sys"

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        assert (tmp_path / "no-session").is_dir()

    async def test_oserror_on_write_logs_warning_no_raise(self, tmp_path, caplog):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id="s_err", run_id="r_err")
        state = make_state(messages=[HumanMessage(content="hi")])
        hook._last_system_prompt = "sys"

        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            with caplog.at_level(logging.WARNING):
                # Me must not raise
                await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        assert any("telemetry_write_failed" in r.message for r in caplog.records)

    async def test_custom_base_dir_constructor(self, tmp_path):
        custom_dir = tmp_path / "custom_telemetry"
        hook = TelemetryHook(base_dir=custom_dir)
        ctx = make_ctx(session_id="s_custom", run_id="r_custom")
        state = make_state(messages=[HumanMessage(content="hi")])
        hook._last_system_prompt = "sys"

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        assert (custom_dir / "s_custom").is_dir()

    async def test_uses_state_system_prompt_as_fallback(self, tmp_path):
        """Me if wrap_model_call never called, use state.system_prompt."""
        hook = TelemetryHook(base_dir=tmp_path)
        ctx = make_ctx(session_id="s_fb", run_id="r_fb")
        state = make_state(system_prompt="fallback prompt")
        # Me _last_system_prompt is empty string by default

        await hook.after_agent(ctx, state, AssistantMessage(content="ok"))

        out_file = next((tmp_path / "s_fb").iterdir())
        lines = out_file.read_text().strip().split("\n")
        first = json.loads(lines[0])
        assert first["content"] == "fallback prompt"

    async def test_multiple_turns_create_multiple_files(self, tmp_path):
        hook = TelemetryHook(base_dir=tmp_path)
        ctx1 = make_ctx(session_id="s_multi", run_id="run_1")
        ctx2 = make_ctx(session_id="s_multi", run_id="run_2")

        msg1 = HumanMessage(content="first")
        msg1.db_id = UUID("11111111-1111-1111-1111-111111111111")
        msg2 = HumanMessage(content="second")
        msg2.db_id = UUID("22222222-2222-2222-2222-222222222222")

        state1 = make_state(messages=[msg1])
        state2 = make_state(messages=[msg1, AssistantMessage(content="ok"), msg2])

        hook._last_system_prompt = "sys"
        await hook.after_agent(ctx1, state1, AssistantMessage(content="ok"))
        hook._last_system_prompt = "sys"
        await hook.after_agent(ctx2, state2, AssistantMessage(content="ok"))

        files = list((tmp_path / "s_multi").iterdir())
        assert len(files) == 2
