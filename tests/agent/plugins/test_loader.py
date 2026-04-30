"""Tests for the user-defined plugin loader.

Covers the two authoring contracts the loader recognises (functional
``async def plugin()`` and ``class Plugin(BaseAgentHook)``), rejection
of ill-formed modules, the ``applies_to`` filter, args mutation and
abort semantics for ``tool.before``, and isolation: a single broken
plugin must never crash discovery for the rest.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from app.agent.hooks.base import BaseAgentHook
from app.agent.plugins.loader import _FunctionalPluginAdapter, load_plugin_hooks
from app.agent.schemas.chat import FunctionCall, ToolCall
from app.agent.state import AgentState, RunContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx() -> RunContext:
    return RunContext(session_id="s", run_id="r", agent_name="bot")


def _state() -> AgentState:
    return AgentState(messages=[])


def _tool_call(name: str = "shell", args: dict | None = None) -> ToolCall:
    return ToolCall(
        id="call-1",
        function=FunctionCall(
            name=name,
            arguments=json.dumps(args if args is not None else {}),
        ),
    )


def _write(plugin_dir: Path, name: str, body: str) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / name).write_text(dedent(body).lstrip())


# ---------------------------------------------------------------------------
# Discovery + contract recognition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_functional_plugin_loaded(tmp_path: Path) -> None:
    """Functional ``async def plugin()`` returning event dict is loaded."""
    _write(
        tmp_path,
        "fn_plugin.py",
        """
        async def plugin():
            async def before(input, output):
                output["args"]["sentinel"] = "yes"

            return {"tool.before": before}
        """,
    )

    hooks = await load_plugin_hooks([tmp_path], agent_name="a", role="lead")
    assert len(hooks) == 1
    assert isinstance(hooks[0], _FunctionalPluginAdapter)


@pytest.mark.asyncio
async def test_class_plugin_loaded(tmp_path: Path) -> None:
    """Module exposing ``class Plugin(BaseAgentHook)`` is instantiated."""
    _write(
        tmp_path,
        "cls_plugin.py",
        """
        from app.agent.hooks.base import BaseAgentHook

        class Plugin(BaseAgentHook):
            calls = 0
        """,
    )

    hooks = await load_plugin_hooks([tmp_path], agent_name="a", role="lead")
    assert len(hooks) == 1
    assert isinstance(hooks[0], BaseAgentHook)
    # Same module loaded twice should produce a fresh instance each time
    # (no shared mutable state across reloads).
    hooks2 = await load_plugin_hooks([tmp_path], agent_name="a", role="lead")
    assert hooks2[0] is not hooks[0]


@pytest.mark.asyncio
async def test_underscore_files_skipped(tmp_path: Path) -> None:
    """Files prefixed with ``_`` are treated as helper modules and skipped."""
    _write(
        tmp_path,
        "_helper.py",
        """
        from app.agent.hooks.base import BaseAgentHook

        class Plugin(BaseAgentHook):
            pass
        """,
    )
    hooks = await load_plugin_hooks([tmp_path], agent_name="a", role="lead")
    assert hooks == []


@pytest.mark.asyncio
async def test_broken_plugin_does_not_block_others(tmp_path: Path) -> None:
    """A plugin that raises at import time is logged and skipped, not raised."""
    _write(tmp_path, "broken.py", "raise RuntimeError('boom at import')")
    _write(
        tmp_path,
        "ok.py",
        """
        from app.agent.hooks.base import BaseAgentHook

        class Plugin(BaseAgentHook):
            pass
        """,
    )
    hooks = await load_plugin_hooks([tmp_path], agent_name="a", role="lead")
    # ``broken.py`` is dropped; ``ok.py`` survives.
    assert len(hooks) == 1


@pytest.mark.asyncio
async def test_unrecognised_module_skipped(tmp_path: Path) -> None:
    """A module exposing neither ``plugin`` nor ``Plugin`` is rejected gracefully."""
    _write(tmp_path, "noop.py", "x = 1\n")
    hooks = await load_plugin_hooks([tmp_path], agent_name="a", role="lead")
    assert hooks == []


@pytest.mark.asyncio
async def test_missing_dir_returns_empty(tmp_path: Path) -> None:
    """Non-existent plugin dirs are tolerated silently."""
    hooks = await load_plugin_hooks(
        [tmp_path / "does-not-exist"], agent_name="a", role="lead"
    )
    assert hooks == []


# ---------------------------------------------------------------------------
# applies_to filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_applies_to_excludes_non_matching_agent(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scoped.py",
        """
        from app.agent.hooks.base import BaseAgentHook

        class Plugin(BaseAgentHook):
            def applies_to(self, agent_name, role):
                return agent_name == "matched"
        """,
    )
    matched = await load_plugin_hooks([tmp_path], agent_name="matched", role="lead")
    other = await load_plugin_hooks([tmp_path], agent_name="other", role="lead")
    assert len(matched) == 1
    assert other == []


@pytest.mark.asyncio
async def test_functional_applies_to_excludes_role(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "role_scoped.py",
        """
        async def plugin():
            def applies_to(agent_name, role):
                return role == "member"

            async def before(input, output):
                pass

            return {
                "tool.before": before,
                "applies_to": applies_to,
            }
        """,
    )
    leads = await load_plugin_hooks([tmp_path], agent_name="a", role="lead")
    members = await load_plugin_hooks([tmp_path], agent_name="a", role="member")
    assert leads == []
    assert len(members) == 1


# ---------------------------------------------------------------------------
# Functional adapter — args mutation, abort, after-hook
# ---------------------------------------------------------------------------


async def _run_through_adapter(
    adapter: _FunctionalPluginAdapter,
    tc: ToolCall,
    *,
    inner_result: str = "ok",
) -> tuple[str, ToolCall]:
    """Run the adapter's ``wrap_tool_call`` against a stub inner handler.

    Returns ``(result, tool_call_seen_by_inner_handler)`` so tests can
    assert what the executor would actually have received.
    """
    seen: list[ToolCall] = []

    async def inner(ctx, state, t):
        seen.append(t)
        return inner_result

    result = await adapter.wrap_tool_call(_ctx(), _state(), tc, inner)
    return result, seen[-1] if seen else tc


@pytest.mark.asyncio
async def test_before_hook_can_mutate_args() -> None:
    async def before(input, output):
        if input["tool"] == "shell":
            output["args"]["command"] = "set -e\n" + output["args"]["command"]

    adapter = _FunctionalPluginAdapter(
        plugin_id="t",
        handlers={"tool.before": before},
    )
    tc = _tool_call(args={"command": "echo hi"})
    _, observed = await _run_through_adapter(adapter, tc)
    assert json.loads(observed.function.arguments)["command"] == "set -e\necho hi"


@pytest.mark.asyncio
async def test_before_hook_raise_aborts_execution() -> None:
    inner_called = False

    async def before(input, output):
        raise PermissionError("blocked")

    async def inner(ctx, state, t):
        nonlocal inner_called
        inner_called = True
        return "should-not-run"

    adapter = _FunctionalPluginAdapter(
        plugin_id="t",
        handlers={"tool.before": before},
    )
    result = await adapter.wrap_tool_call(_ctx(), _state(), _tool_call(), inner)
    assert "blocked" in result
    assert result.startswith("Error:")
    assert inner_called is False


@pytest.mark.asyncio
async def test_after_hook_can_rewrite_result() -> None:
    async def after(input, output):
        output["output"] = output["output"].upper()

    adapter = _FunctionalPluginAdapter(
        plugin_id="t",
        handlers={"tool.after": after},
    )
    result, _ = await _run_through_adapter(adapter, _tool_call(), inner_result="hello")
    assert result == "HELLO"


@pytest.mark.asyncio
async def test_after_hook_failure_falls_back_to_original_result() -> None:
    async def after(input, output):
        raise RuntimeError("post boom")

    adapter = _FunctionalPluginAdapter(
        plugin_id="t",
        handlers={"tool.after": after},
    )
    # Hook errors in the *after* phase must not poison the result the
    # executor already produced — we'd rather lose the rewrite than the
    # tool output.
    result, _ = await _run_through_adapter(adapter, _tool_call(), inner_result="raw")
    assert result == "raw"


@pytest.mark.asyncio
async def test_no_handlers_is_pure_passthrough() -> None:
    """An adapter with empty handlers must not touch the ToolCall identity."""
    adapter = _FunctionalPluginAdapter(plugin_id="t", handlers={})
    original = _tool_call(args={"command": "noop"})
    _, observed = await _run_through_adapter(adapter, original)
    assert observed is original


@pytest.mark.asyncio
async def test_unknown_event_keys_are_ignored(tmp_path: Path) -> None:
    """Unknown event names log a warning but the plugin still loads."""
    _write(
        tmp_path,
        "unknown_event.py",
        """
        async def plugin():
            async def before(input, output):
                pass

            async def stranger(input, output):
                pass

            return {
                "tool.before": before,
                "future.event.name": stranger,
            }
        """,
    )
    hooks = await load_plugin_hooks([tmp_path], agent_name="a", role="lead")
    assert len(hooks) == 1


# ---------------------------------------------------------------------------
# Multi-dir dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_dirs_loaded_in_order(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    _write(
        a,
        "first.py",
        """
        from app.agent.hooks.base import BaseAgentHook

        class Plugin(BaseAgentHook):
            origin = "a"
        """,
    )
    _write(
        b,
        "second.py",
        """
        from app.agent.hooks.base import BaseAgentHook

        class Plugin(BaseAgentHook):
            origin = "b"
        """,
    )
    hooks = await load_plugin_hooks([a, b], agent_name="x", role="lead")
    origins = [getattr(h, "origin", None) for h in hooks]
    assert origins == ["a", "b"]
