"""StreamPublisherHook — publishes agent events to the shared stream store.

Reuses the same stream_store.push_event() / mark_done() infrastructure as the
single-agent chat route, so the team SSE stream is identical in shape to the
single-agent stream.  The frontend can subscribe to GET /team/stream/{session_id}
and receive exactly the same event types it already handles.

All events carry an ``agent`` field so the frontend can distinguish who is
speaking when multiple members are active simultaneously.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING


from app.agent.hooks.base import BaseAgentHook
from app.agent.tool_id_resolver import ToolIdResolver
from app.services import memory_stream_store as stream_store
from app.agent.schemas.events import (
    MessageEvent,
    PermissionAskedEvent,
    RateLimitEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolEndEvent,
    ToolStartEvent,
    UsageEvent,
)
from app.services.stream_envelope import AnyStreamEvent, StreamEnvelope

if TYPE_CHECKING:
    from app.agent.schemas.chat import AssistantMessage, ChatCompletionChunk, ToolCall
    from app.agent.state import AgentState, RunContext, ToolCallHandler


class StreamPublisherHook(BaseAgentHook):
    """Publishes every agent event to the stream store via stream_store.push_event().

    Designed for team members: each member gets its own instance bound to the
    shared lead session_id so all agents write to the same stream key,
    and the frontend receives a unified event feed tagged by agent name.

    ``mark_done`` is intentionally NOT called here — the team coordinator
    (AgentTeam) calls it once after all members are idle, not per-member.

    Args:
        session_id: The stream key suffix (team lead's session_id).
        agent_name: Name of the agent this hook is attached to.
    """

    def __init__(self, session_id: str, agent_name: str) -> None:
        self._session_id = session_id
        self._agent_name = agent_name
        self._resolver = ToolIdResolver()
        # Me track per-turn usage for turn-total summary
        self._total_prompt = 0
        self._total_completion = 0
        self._total_cached: int | None = None
        self._total_thoughts: int | None = None
        self._total_tool_use: int | None = None
        self._usage_count = 0
        self._used_models: set[str] = set()

    async def _push(self, event: AnyStreamEvent) -> None:
        """Fire-and-forget push to stream store. Never raises."""
        with contextlib.suppress(Exception):
            await stream_store.push_event(
                self._session_id, StreamEnvelope.from_event(event)
            )

    async def on_model_delta(
        self, ctx: "RunContext", state: "AgentState", chunk: "ChatCompletionChunk"
    ) -> None:
        if chunk.usage:
            u = chunk.usage
            pt = u.prompt_tokens or 0
            ct = u.completion_tokens or 0
            metadata: dict = {"agent": self._agent_name}
            if chunk.model:
                self._used_models.add(chunk.model)
                metadata["model"] = chunk.model
            await self._push(
                UsageEvent(
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=u.total_tokens or (pt + ct),
                    cached_tokens=getattr(u, "cached_tokens", None),
                    thoughts_tokens=getattr(u, "thoughts_tokens", None),
                    tool_use_tokens=getattr(u, "tool_use_tokens", None),
                    metadata=metadata,
                )
            )
            # Me accumulate for turn-total summary
            self._total_prompt += pt
            self._total_completion += ct
            cached = getattr(u, "cached_tokens", None)
            if cached is not None:
                self._total_cached = (self._total_cached or 0) + cached
            thoughts = getattr(u, "thoughts_tokens", None)
            if thoughts is not None:
                self._total_thoughts = (self._total_thoughts or 0) + thoughts
            tool_use = getattr(u, "tool_use_tokens", None)
            if tool_use is not None:
                self._total_tool_use = (self._total_tool_use or 0) + tool_use
            self._usage_count += 1

        if not chunk.choices:
            return

        delta = chunk.choices[0].delta

        if delta.reasoning_content:
            await self._push(
                ThinkingEvent(agent=self._agent_name, text=delta.reasoning_content)
            )

        if delta.content:
            await self._push(MessageEvent(agent=self._agent_name, text=delta.content))

        for tc in delta.tool_calls or []:
            fn_name = tc.function.name if tc.function and tc.function.name else ""
            if not fn_name:
                continue
            tc_id = tc.id or f"{self._agent_name}:{fn_name}:{tc.index}"
            if not self._resolver.register(fn_name, tc_id):
                continue
            await self._push(
                ToolCallEvent(
                    agent=self._agent_name,
                    tool_call_id=tc_id,
                    name=fn_name,
                )
            )

    async def wrap_tool_call(
        self,
        ctx: "RunContext",
        state: "AgentState",
        tool_call: "ToolCall",
        handler: "ToolCallHandler",
    ) -> str:
        import json as _json

        from app.agent.permission import (
            PermissionDeniedError,
            PermissionRejectedError,
            get_permission_service,
        )

        fn_name = tool_call.function.name if tool_call.function else ""
        tc_id = self._resolver.resolve_start(fn_name, tool_call.id)

        # ── Permission check before tool execution ────────────────────
        # Extract a human-readable "command pattern" from the tool arguments
        # so the permission system can show the user what the agent wants to do.
        try:
            args_dict: dict = (
                _json.loads(tool_call.function.arguments or "{}")
                if tool_call.function
                else {}
            )
        except Exception:
            args_dict = {}

        # Build patterns: use the command/path argument if present, else tool name
        patterns: list[str] = []
        if "command" in args_dict:
            # Extract the command prefix (first 1-3 tokens, matching opencode's BashArity)
            cmd_str = str(args_dict["command"]).strip()
            patterns.append(cmd_str[:200] if cmd_str else fn_name)
        elif "path" in args_dict or "file_path" in args_dict:
            p = args_dict.get("path") or args_dict.get("file_path") or fn_name
            patterns.append(str(p))
        else:
            patterns.append(fn_name)

        permission_service = get_permission_service()

        # Fire SSE events for ask/reply (even in auto-allow mode)
        def _on_ask_callback(req):
            """Fire-and-forget SSE event when permission is requested."""
            import asyncio as _asyncio
            import contextlib as _contextlib

            async def _emit():
                with _contextlib.suppress(Exception):
                    await stream_store.push_event(
                        self._session_id,
                        StreamEnvelope.from_event(
                            PermissionAskedEvent(
                                request_id=req.id,
                                session_id=self._session_id,
                                tool=fn_name,
                                patterns=req.patterns,
                                metadata=req.metadata,
                            )
                        ),
                    )

            # Schedule without blocking wrap_tool_call
            _asyncio.create_task(_emit())

        # Temporarily attach SSE callback for this call
        original_on_ask = permission_service._on_ask
        permission_service._on_ask = _on_ask_callback
        try:
            await permission_service.ask(
                tool=fn_name,
                patterns=patterns,
                always_patterns=patterns,
                metadata={"tool_call_id": tc_id, "agent": self._agent_name},
            )
        except (PermissionDeniedError, PermissionRejectedError):
            permission_service._on_ask = original_on_ask
            raise
        finally:
            permission_service._on_ask = original_on_ask

        # ── Execute tool ──────────────────────────────────────────────
        await self._push(
            ToolStartEvent(
                agent=self._agent_name,
                tool_call_id=tc_id,
                name=fn_name,
                arguments=tool_call.function.arguments if tool_call.function else None,
            )
        )
        result = await handler(ctx, state, tool_call)
        tc_id = self._resolver.resolve_end(tool_call.id)
        await self._push(
            ToolEndEvent(
                agent=self._agent_name,
                tool_call_id=tc_id,
                name=fn_name,
                result=result or None,
            )
        )
        return result

    async def on_rate_limit(
        self,
        ctx: "RunContext",
        state: "AgentState",
        retry_after: int,
        attempt: int,
        max_attempts: int,
    ) -> None:
        await self._push(
            RateLimitEvent(
                retry_after=retry_after,
                attempt=attempt,
                max_attempts=max_attempts,
            )
        )

    async def after_agent(
        self, ctx: "RunContext", state: "AgentState", response: "AssistantMessage"
    ) -> None:
        # Me emit turn-total usage summary when multiple model calls were made
        if self._usage_count > 1 and (self._total_prompt or self._total_completion):
            await self._push(
                UsageEvent(
                    prompt_tokens=self._total_prompt,
                    completion_tokens=self._total_completion,
                    total_tokens=self._total_prompt + self._total_completion,
                    cached_tokens=self._total_cached,
                    thoughts_tokens=self._total_thoughts,
                    tool_use_tokens=self._total_tool_use,
                    metadata={
                        "turn_total": True,
                        "agent": self._agent_name,
                        "models": sorted(self._used_models) or None,
                    },
                )
            )
        # Me reset counters so hook can be reused across turns
        self._total_prompt = 0
        self._total_completion = 0
        self._total_cached = None
        self._total_thoughts = None
        self._total_tool_use = None
        self._usage_count = 0
        self._used_models = set()
