"""Core :class:`Agent` class — orchestrates one ``run()`` per turn.

The class itself is now thin: it owns construction, the iteration
loop, the hook plumbing, and the per-iteration bookkeeping.  Each
substantial piece of work is delegated to a sibling module:

- :mod:`app.agent.agent_loop.streaming` — stream + assemble one LLM call
- :mod:`app.agent.agent_loop.retry` — retry / fallback over a provider
- :mod:`app.agent.agent_loop.tool_executor` — innermost tool executor
- :mod:`app.agent.agent_loop.tool_dispatch` — parallel tool-call gather
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Generic, TypeVar
from uuid import uuid7 as _uuid7

from loguru import logger

from app.agent.agent_loop.streaming import stream_and_assemble
from app.agent.agent_loop.tool_dispatch import gather_or_cancel
from app.agent.agent_loop.tool_executor import make_tool_executor
from app.agent.checkpointer import Checkpointer
from app.agent.hooks import BaseAgentHook
from app.agent.providers.base import LLMProviderBase
from app.agent.providers.capabilities import ModelCapabilities, get_capabilities
from app.agent.schemas.agent import (
    AgentContext,
    AgentStats,
    RunConfig,
    SummarizationConfig,
)
from app.agent.schemas.chat import (
    AssistantMessage,
    ChatMessage,
    ContentBlock,
    SystemMessage,
    ToolMessage,
    Usage,
)
from app.agent.state import (
    AgentState,
    ModelRequest,
    RunContext,
    ToolCallHandler,
    build_model_chain,
    build_tool_chain,
)
from app.agent.tools.registry import Tool

MAX_AGENT_ITERATIONS = 100
MAX_CONCURRENT_TOOLS = 10

TContext = TypeVar("TContext", bound=AgentContext)


class Agent(Generic[TContext]):
    """Core agent with a flat, simple API.

    ``TContext`` is an optional :class:`~app.schemas.agent.AgentContext` subclass
    that carries typed, validated per-invocation data (user role, locale, etc.).
    Hooks can read ``state.context`` with full IDE autocomplete.

    Example::

        class UserContext(AgentContext):
            user_group: str = "default"

        agent = Agent(
            llm_provider=GoogleGenAIProvider(api_key="...", model="gemini-3.1-flash", temperature=0.7),
            name="assistant",
            system_prompt="You are a helpful assistant.",
            tools=[web_search, get_date],
            hooks=[DatabaseHook(session_factory)],
            context=UserContext(user_group="premium"),
        )
    """

    def __init__(
        self,
        llm_provider: LLMProviderBase,
        name: str = "Agent",
        description: str | None = None,
        system_prompt: str = "You are a helpful assistant.",
        tools: list[Tool] | None = None,
        skills: list[str] | None = None,
        mcp_servers: list[str] | None = None,
        hooks: Sequence[BaseAgentHook] | None = None,
        max_iterations: int = MAX_AGENT_ITERATIONS,
        context: TContext | None = None,
        max_concurrent_tools: int = MAX_CONCURRENT_TOOLS,
        model_id: str | None = None,
        fallback_provider: LLMProviderBase | None = None,
        fallback_model_id: str | None = None,
        summarization_config: SummarizationConfig | None = None,
    ):
        self.id = _uuid7()
        self.name = name
        self.description = description
        self.llm_provider = llm_provider
        # Me store original "provider:model" string from config
        self.model_id = model_id
        # Me cache multimodal capabilities — computed once from model_id
        self.capabilities: ModelCapabilities = get_capabilities(model_id)
        self.system_prompt = system_prompt
        self.skills: list[str] = list(skills) if skills else []
        # MCP server names this agent was configured with (from `mcp:` frontmatter).
        # Surface to API consumers so the UI can group tools by origin server,
        # including servers that exist but aren't ready yet (zero tools).
        self.mcp_servers: list[str] = list(mcp_servers) if mcp_servers else []
        self.hooks: list[BaseAgentHook] = list(hooks) if hooks else []
        self.max_iterations = max_iterations
        self.context = context
        self.run_config: RunConfig | None = None
        self._tool_semaphore = asyncio.Semaphore(max_concurrent_tools)
        # Cumulative agent-level statistics (updated per run)
        self.stats = AgentStats(agent_id=self.id)
        # Fallback provider — used when primary exhausts retries on retryable errors
        self.fallback_provider: LLMProviderBase | None = fallback_provider
        self.fallback_model_id: str | None = fallback_model_id
        self.summarization_config = summarization_config

        # Build internal tool lookup from Tool objects or plain callables
        self._tools: dict[str, Tool] = {}
        for fn in tools or []:
            t = fn if isinstance(fn, Tool) else Tool(fn)
            self._tools[t.name] = t

        # Drift tracking (set by loader._build_agent for disk-loaded agents).
        self.source_path: Path | None = None
        self.config_stamp: dict[str, int | None] = {}

        # User-defined plugin hooks loaded from settings.OPENAGENTD_PLUGINS_DIRS.
        # Cached on first run() so import + applies_to filtering happens once.
        # Keyed by role so the same Agent instance reused across roles
        # (theoretical) wouldn't cross-contaminate.
        self._plugin_hooks_by_role: dict[str, list[BaseAgentHook]] = {}

    async def _load_plugin_hooks(self, role: str) -> list[BaseAgentHook]:
        """Lazily load and cache user-defined plugin hooks for ``role``.

        Discovery + import happens at most once per ``(self, role)`` pair.
        Plugin failures are logged inside the loader and never propagate
        — a broken plugin must not break the agent.
        """
        cached = self._plugin_hooks_by_role.get(role)
        if cached is not None:
            return cached

        # Local imports keep cold-import cost off the hot path and avoid
        # forcing every test that constructs an Agent to set up the
        # plugins package.
        from app.agent.plugins import load_plugin_hooks
        from app.core.config import settings

        try:
            hooks = await load_plugin_hooks(
                settings.plugin_dirs(),
                agent_name=self.name,
                role=role,
            )
        except Exception as exc:  # noqa: BLE001 — defensive, never break agent
            logger.warning(
                "plugin_load_pipeline_failed agent={} error={}", self.name, exc
            )
            hooks = []

        self._plugin_hooks_by_role[role] = hooks
        return hooks

    async def run(
        self,
        messages: list[ChatMessage],
        config: RunConfig | None = None,
        *,
        hooks: Sequence[BaseAgentHook] | None = None,
        injected_tools: list[Tool] | None = None,
        interrupt_event: asyncio.Event | None = None,
        checkpointer: Checkpointer | None = None,
        **kwargs,
    ) -> list[ChatMessage]:
        """Runs the agent loop for a single turn.

        Returns the full list of messages produced.

        ``hooks`` provides additional hooks for this run, combined with the
        agent's default ``self.hooks``.

        ``injected_tools`` provides additional tools for this specific run only,
        merged with the agent's constructor tools. Callers should use this
        instead of mutating ``agent._tools`` directly.

        ``checkpointer`` is an optional :class:`~app.agent.checkpointer.Checkpointer`
        that the loop calls at defined sync points to persist state.  When
        provided, ``DatabaseHook`` is not needed — the loop owns persistence.

        Agent role for plugin ``applies_to`` filtering is read from the
        :mod:`app.agent.plugins.role` contextvar — team callers wrap the
        ``run()`` invocation with :func:`set_role`.
        """
        from app.agent.plugins.role import current_role

        role = current_role()
        self.run_config = config
        plugin_hooks = await self._load_plugin_hooks(role)
        combined_hooks = list(self.hooks) + list(hooks or []) + plugin_hooks

        # Build run-local tool lookup: constructor tools + injected_tools.
        # Never mutate self._tools so concurrent runs are safe.
        run_tools: dict[str, Tool] = dict(self._tools)
        for t in injected_tools or []:
            run_tools[t.name] = t

        # Work on a local copy, strip any SystemMessage — system prompt lives
        # in state.system_prompt and is prepended per-call by the loop.
        messages = [m for m in messages if not isinstance(m, SystemMessage)]

        # Me build immutable run context — identity that no change mid-run
        ctx = RunContext(
            session_id=config.session_id if config else None,
            run_id=config.run_id if config else str(_uuid7()),
            agent_name=self.name,
            session_created_at=config.session_created_at if config else None,
        )

        # Build per-run AgentState — passed to all hooks throughout the loop
        state = AgentState(
            messages=messages,
            system_prompt=self.system_prompt,
            context=self.context,
            capabilities=self.capabilities,
            tool_names=sorted(run_tools.keys()),
        )

        # Expose session_id in state.metadata so tools (e.g. note) can read it
        # without needing direct access to RunContext.
        if ctx.session_id is not None:
            state.metadata["session_id"] = ctx.session_id

        # Me seed last_prompt_tokens from checkpointer so SummarizationHook
        # fires on session resume without call-site workaround
        if checkpointer is not None and ctx.session_id is not None:
            checkpointer.seed_state(ctx.session_id, state)  # no-op by default

        self.stats.status = "running"
        run_start = time.monotonic()
        logger.info(
            "agent_run_start agent={} message_count={} tools={} session={}",
            self.name,
            len(messages),
            len(run_tools),
            ctx.session_id,
        )

        for hook in combined_hooks:
            await hook.before_agent(ctx, state)

        last_assistant_msg: AssistantMessage | None = None
        tool_defs = [t.definition for t in run_tools.values()]

        # Build tool execution chain — all hooks participate via wrap_tool_call
        tool_chain: ToolCallHandler = build_tool_chain(
            combined_hooks,
            make_tool_executor(run_tools, self.name),
        )

        iteration = 0
        total_tokens = 0
        # Streaming returns ``last_usage`` per call; the loop tracks the latest
        # value so it can fold it into per-iteration logging and ``state.usage``.
        last_usage: Usage | None = None

        while iteration < self.max_iterations:
            iteration += 1
            iter_start = time.monotonic()
            logger.info(
                "agent_iteration agent={} iteration={}/{} messages={}",
                self.name,
                iteration,
                self.max_iterations,
                len(messages),
            )
            # Build per-iteration ModelRequest — immutable view of what LLM sees.
            # messages_for_llm excludes SystemMessage + excluded messages.
            model_request = ModelRequest(
                messages=tuple(state.messages_for_llm),
                system_prompt=state.system_prompt,
                context=state.context,
            )

            # before_model: hooks may return a modified ModelRequest.
            # SummarizationHook mutates state.messages and returns updated messages
            # in the new ModelRequest — so the current LLM call sees the summary.
            for hook in combined_hooks:
                updated = await hook.before_model(ctx, state, model_request)
                if updated is not None:
                    model_request = updated

            # Me sync after before_model — persists summarization changes
            await self._sync(checkpointer, ctx, state)

            # Build wrap_model_call chain and invoke it
            iter_usage_holder: list[Usage | None] = [None]

            async def _stream(req: ModelRequest) -> AssistantMessage:
                msg, usage = await stream_and_assemble(
                    req=req,
                    ctx=ctx,
                    state=state,
                    hooks=combined_hooks,
                    interrupt_event=interrupt_event,
                    tool_defs=tool_defs,
                    primary_provider=self.llm_provider,
                    primary_label=self.model_id or "primary",
                    fallback_provider=self.fallback_provider,
                    fallback_label=self.fallback_model_id or "fallback",
                    agent_name=self.name,
                    agent_id=str(self.id),
                )
                iter_usage_holder[0] = usage
                return msg

            model_chain = build_model_chain(combined_hooks, ctx, state, _stream)
            assistant_msg = await model_chain(model_request)

            tc_list = assistant_msg.tool_calls or []
            last_usage = iter_usage_holder[0]
            stream_elapsed = time.monotonic() - iter_start

            logger.info(
                "llm_response agent={} iteration={} elapsed={:.2f}s "
                "content_len={} reasoning_len={} tool_calls={} tokens={}/{}/{}",
                self.name,
                iteration,
                stream_elapsed,
                len(assistant_msg.content or ""),
                len(assistant_msg.reasoning_content or ""),
                len(tc_list),
                last_usage.prompt_tokens if last_usage else 0,
                last_usage.completion_tokens if last_usage else 0,
                last_usage.total_tokens if last_usage else 0,
            )

            # Me attach usage to message + state (single dict, shared reference)
            if last_usage:
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
                assistant_msg.extra = {"usage": usage_dict}
                total_tokens += last_usage.total_tokens
                state.usage.last_prompt_tokens = last_usage.prompt_tokens
                state.usage.last_completion_tokens = last_usage.completion_tokens
                state.usage.total_tokens = total_tokens
                state.usage.last_usage = usage_dict
                state.metadata["total_tokens"] = total_tokens
                state.metadata["last_usage"] = usage_dict

            messages.append(assistant_msg)
            last_assistant_msg = assistant_msg
            self.stats.messages_count += 1

            for hook in combined_hooks:
                await hook.after_model(ctx, state, assistant_msg)

            # Me sync after after_model — captures assistant message + usage
            await self._sync(checkpointer, ctx, state)

            # Me check sleep sentinel before deciding whether to continue
            _is_sleep = (assistant_msg.content or "").strip() in ("<sleep>", "[sleep]")

            if not tc_list:
                logger.info(
                    "agent_iteration_done agent={} iteration={} action={}",
                    self.name,
                    iteration,
                    "sleep" if _is_sleep else "final_response",
                )
                break

            # Pre-dispatch interrupt check — skip tool execution entirely
            if interrupt_event is not None and interrupt_event.is_set():
                logger.info(
                    "tool_dispatch_skipped_interrupt agent={} count={}",
                    self.name,
                    len(tc_list),
                )
                for tc in tc_list:
                    messages.append(
                        ToolMessage(
                            content="Cancelled by user.",
                            tool_call_id=tc.id,
                            name=tc.function.name,
                        )
                    )
                break

            logger.info(
                "tool_dispatch agent={} count={} tools=[{}]",
                self.name,
                len(tc_list),
                ", ".join(tc.function.name for tc in tc_list),
            )

            # Execute tool calls in parallel, cancelling on interrupt
            results = await gather_or_cancel(
                [self._run_tool(ctx, state, tc, tool_chain) for tc in tc_list],
                interrupt_event,
                tc_list,
                self.name,
            )

            # Retrieve any multimodal parts stashed by ToolResult-returning tools
            multimodal_parts: dict[str, list[ContentBlock]] = state.metadata.pop(
                "_multimodal_tool_parts", {}
            )

            cancelled = interrupt_event is not None and interrupt_event.is_set()
            for item in results:
                if isinstance(item, BaseException):
                    logger.error("tool_gather_error error={}", item)
                    continue
                tc, result = item
                tool_msg = ToolMessage(
                    content=result, tool_call_id=tc.id, name=tc.function.name
                )
                # Attach multimodal parts if the tool returned a ToolResult
                if tc.id in multimodal_parts:
                    tool_msg.parts = multimodal_parts[tc.id]
                messages.append(tool_msg)

            if cancelled:
                break

            # Me sync after tool execution — captures tool results
            await self._sync(checkpointer, ctx, state)

            # Me sleep + tool calls: tools executed, now exit without another LLM call
            if _is_sleep:
                logger.info(
                    "agent_iteration_done agent={} iteration={} action=sleep_after_tools",
                    self.name,
                    iteration,
                )
                break

        if last_assistant_msg:
            for hook in combined_hooks:
                await hook.after_agent(ctx, state, last_assistant_msg)

        # Me sync after after_agent — final sync
        await self._sync(checkpointer, ctx, state)

        self.stats.status = "completed"
        self.stats.total_tokens += total_tokens
        self.run_config = None
        run_elapsed = time.monotonic() - run_start
        logger.info(
            "agent_run_done agent={} elapsed={:.2f}s iterations={} "
            "total_messages={} total_tokens={} has_response={}",
            self.name,
            run_elapsed,
            iteration,
            len(messages),
            total_tokens,
            last_assistant_msg is not None,
        )
        return messages

    async def _run_tool(
        self,
        ctx: RunContext,
        state: AgentState,
        tc,
        chain: ToolCallHandler,
    ) -> tuple:
        """Execute a single tool call through the hook chain (semaphore-bounded)."""
        async with self._tool_semaphore:
            result = await chain(ctx, state, tc)
            return tc, result

    @staticmethod
    async def _sync(
        checkpointer: Checkpointer | None,
        ctx: RunContext,
        state: AgentState,
    ) -> None:
        """Call checkpointer.sync() if a checkpointer is configured."""
        if checkpointer is None or ctx.session_id is None:
            return
        try:
            await checkpointer.sync(ctx, state)
        except Exception as exc:
            logger.error(
                "checkpointer_sync_failed session_id={} error={}",
                ctx.session_id,
                exc,
            )
