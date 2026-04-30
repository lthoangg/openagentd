"""Stream one LLM call and assemble the response into an :class:`AssistantMessage`.

The provider yields a sequence of OpenAI-style chat-completion chunks.
This module concatenates the textual content + reasoning, re-assembles
fragmented tool-call deltas back into whole :class:`ToolCall` objects,
and folds usage information into the final message.

Returns ``(AssistantMessage, last_usage)`` so the caller (``Agent.run``)
can both publish the message and update its rolling usage stats.

Lives outside the :class:`Agent` class because it depends only on the
agent's identity (name + id) for tagging the produced message — no
mutable instance state — which keeps the loop thin and the streaming
logic individually testable.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from loguru import logger

from app.agent.agent_loop.retry import stream_with_retry
from app.agent.schemas.chat import (
    AssistantMessage,
    ChatMessage,
    SystemMessage,
    ToolCall,
    Usage,
)

if TYPE_CHECKING:
    from app.agent.hooks import BaseAgentHook
    from app.agent.providers.base import LLMProviderBase
    from app.agent.state import AgentState, ModelRequest, RunContext


async def stream_and_assemble(
    *,
    req: ModelRequest,
    ctx: RunContext,
    state: AgentState,
    hooks: list[BaseAgentHook],
    interrupt_event: asyncio.Event | None,
    tool_defs: list,
    primary_provider: LLMProviderBase,
    primary_label: str,
    fallback_provider: LLMProviderBase | None,
    fallback_label: str,
    agent_name: str,
    agent_id: str,
) -> tuple[AssistantMessage, Usage | None]:
    """Stream one LLM call and assemble the response.

    The innermost handler passed to ``build_model_chain`` in the
    :class:`~app.agent.agent_loop.Agent`.  Hook ``wrap_model_call``
    wrappers receive a callable bound to this and may modify ``req``
    before forwarding it.

    Returns the assembled :class:`AssistantMessage` plus the last
    :class:`Usage` chunk seen during streaming (so the caller can
    update rolling stats).
    """
    full_content = ""
    reasoning = ""
    tool_calls_buffer: dict[int, dict] = {}
    last_usage: Usage | None = None

    # Prepend SystemMessage from the (possibly hook-modified) prompt.
    provider_messages: list[ChatMessage] = [
        SystemMessage(content=req.system_prompt),
        *req.messages,
    ]

    async for chunk in stream_with_retry(
        primary_provider=primary_provider,
        primary_label=primary_label,
        fallback_provider=fallback_provider,
        fallback_label=fallback_label,
        agent_name=agent_name,
        ctx=ctx,
        state=state,
        hooks=hooks,
        messages=provider_messages,
        tools=tool_defs or None,
    ):
        # Preemptive interrupt: break out of streaming early
        if interrupt_event is not None and interrupt_event.is_set():
            logger.debug("agent_streaming_interrupted agent={}", agent_name)
            break

        for hook in hooks:
            await hook.on_model_delta(ctx, state, chunk)

        if chunk.usage:
            last_usage = chunk.usage

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta

        if delta.reasoning_content:
            reasoning += delta.reasoning_content
        if delta.content:
            full_content += delta.content

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index if tc.index is not None else 0
                # Me warn if different tool call lands in same slot
                if (
                    idx in tool_calls_buffer
                    and tc.id
                    and tool_calls_buffer[idx]["id"]
                    and tc.id != tool_calls_buffer[idx]["id"]
                ):
                    logger.warning(
                        "tool_call_index_collision idx={} existing_id={} new_id={}",
                        idx,
                        tool_calls_buffer[idx]["id"],
                        tc.id,
                    )
                if idx not in tool_calls_buffer:
                    tool_calls_buffer[idx] = {
                        "id": tc.id or "",
                        "function": {
                            "name": tc.function.name
                            if tc.function and tc.function.name
                            else "",
                            "arguments": tc.function.arguments
                            if tc.function and tc.function.arguments
                            else "",
                            "thought": tc.function.thought
                            if tc.function and tc.function.thought
                            else None,
                            "thought_signature": tc.function.thought_signature
                            if tc.function and tc.function.thought_signature
                            else None,
                        },
                    }
                else:
                    # Only update id if not already set — first id wins
                    if tc.id and not tool_calls_buffer[idx]["id"]:
                        tool_calls_buffer[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            if not tool_calls_buffer[idx]["function"]["name"]:
                                tool_calls_buffer[idx]["function"]["name"] = (
                                    tc.function.name
                                )
                        if tc.function.arguments:
                            buf = tool_calls_buffer[idx]["function"]["arguments"]
                            if not buf:
                                tool_calls_buffer[idx]["function"]["arguments"] = (
                                    tc.function.arguments
                                )
                            else:
                                try:
                                    json.loads(buf)
                                except json.JSONDecodeError:
                                    tool_calls_buffer[idx]["function"]["arguments"] += (
                                        tc.function.arguments
                                    )
                        if tc.function.thought:
                            tool_calls_buffer[idx]["function"]["thought"] = (
                                tc.function.thought
                            )
                        if tc.function.thought_signature:
                            tool_calls_buffer[idx]["function"]["thought_signature"] = (
                                tool_calls_buffer[idx]["function"]["thought_signature"]
                                or ""
                            ) + tc.function.thought_signature

    tc_list: list[ToolCall] = [
        ToolCall(**tool_calls_buffer[i]) for i in sorted(tool_calls_buffer)
    ]
    # Me attach usage to `extra` immediately so `wrap_model_call` hooks
    # (e.g. OtelHook) can read it from the returned message inside the
    # chain.  The run loop re-asserts the same mapping — that
    # assignment is now idempotent but kept for clarity and to cover the
    # rare case of a hook replacing `assistant_msg` wholesale.
    extra: dict | None = None
    if last_usage is not None:
        usage_dict: dict = {
            "input": last_usage.prompt_tokens,
            "output": last_usage.completion_tokens,
        }
        if last_usage.cached_tokens is not None:
            usage_dict["cache"] = last_usage.cached_tokens
        if last_usage.thoughts_tokens is not None:
            usage_dict["thoughts"] = last_usage.thoughts_tokens
        if last_usage.tool_use_tokens is not None:
            usage_dict["tool_use"] = last_usage.tool_use_tokens
        extra = {"usage": usage_dict}

    msg = AssistantMessage(
        content=full_content or None,
        reasoning_content=reasoning or None,
        tool_calls=tc_list or None,
        agent_id=agent_id,
        agent_name=agent_name,
        extra=extra,
    )
    return msg, last_usage
