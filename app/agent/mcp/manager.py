"""Long-lived MCP client manager.

Owns one :class:`mcp.ClientSession` per configured server. Sessions are
opened during application startup and kept alive for the server's lifetime,
matching the lifecycle of ``team_manager`` and ``task_scheduler``.

A failed server does NOT block startup: the error is logged, status is set
to ``error``, and the process continues. Healthy servers' tools are merged
into the agent loader's tool registry on next call to
:meth:`MCPManager.get_tools_dict`.

Threading model
---------------

The MCP SDK uses ``anyio`` task groups internally and requires that a
``ClientSession`` is entered and exited from the **same task**. We therefore
spawn one long-running ``asyncio.Task`` per server that:

1. Enters the transport context (``stdio_client`` or ``streamablehttp_client``).
2. Enters the ``ClientSession`` context.
3. Calls ``session.initialize()`` and ``session.list_tools()``.
4. Awaits a shutdown ``Event``.
5. Exits both contexts on the way out.

Tool calls happen in arbitrary other tasks but only ever **read** the live
``ClientSession`` reference; they never enter or exit its context.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger

from app.agent.mcp.config import (
    HttpServerConfig,
    StdioServerConfig,
    load_config,
)
from app.agent.mcp.tools import MCPTool
from app.agent.tools.registry import Tool

if TYPE_CHECKING:
    from mcp import ClientSession


@dataclass
class MCPServerStatus:
    """Live state for one MCP server. Returned by ``GET /api/mcp/servers``."""

    name: str
    transport: str
    enabled: bool
    state: str  # "stopped" | "starting" | "ready" | "error"
    error: str | None = None
    tool_names: list[str] = field(default_factory=list)
    started_at: str | None = None


@dataclass
class _ServerRunner:
    """Holds the asyncio.Task and live session for one MCP server.

    ``task`` is ``None`` for disabled servers (which have nothing to run);
    callers must check before awaiting. The ``ready`` and ``shutdown``
    events stay populated so polling code can treat all runners uniformly.
    """

    shutdown: asyncio.Event
    ready: asyncio.Event
    task: asyncio.Task[None] | None = None
    session: "ClientSession | None" = None
    status: MCPServerStatus = field(
        default_factory=lambda: MCPServerStatus(
            name="", transport="", enabled=False, state="stopped"
        )
    )
    tools: list[MCPTool] = field(default_factory=list)


class MCPManager:
    """Lifecycle owner for all configured MCP server connections.

    Singleton: import :data:`mcp_manager` rather than instantiating directly.
    """

    def __init__(self) -> None:
        self._runners: dict[str, _ServerRunner] = {}
        self._lock = asyncio.Lock()
        self._started = False

    # ── Public lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        """Load ``mcp.json`` and start a connection task per enabled server.

        Safe to call when the file is missing — it just logs and returns.
        Failures on individual servers are logged and do not raise.
        """
        async with self._lock:
            if self._started:
                return
            await self._start_locked()

    async def _start_locked(self) -> None:
        """Body of :meth:`start` — caller must already hold ``self._lock``.

        Factored out so :meth:`reload_from_config` can stop-and-restart in
        a single critical section, closing the window where another caller
        could observe an empty ``_runners`` dict between phases.
        """
        self._started = True

        try:
            cfg = load_config()
        except ValueError as exc:
            logger.error("mcp_config_invalid err={}", exc)
            return

        if not cfg.servers:
            logger.info("mcp_no_servers_configured")
            return

        for name, server_cfg in cfg.servers.items():
            if not server_cfg.enabled:
                self._runners[name] = self._make_disabled_runner(name, server_cfg)
                continue
            await self._spawn_runner(name, server_cfg)

        logger.info(
            "mcp_manager_started servers={}",
            {n: r.status.state for n, r in self._runners.items()},
        )

    async def wait_until_ready(self, *, timeout: float = 10.0) -> None:
        """Block until every spawned runner has reached a terminal state.

        Each runner's ``ready`` event fires when it transitions to ``ready``,
        ``error``, or ``stopped`` — so this returns as soon as every server
        either finished initializing or failed. Servers still pending after
        ``timeout`` are left as-is; the agent loader will see them with zero
        tools and load gracefully (matching :meth:`get_tools_for_server`'s
        existing not-ready contract).

        Called from ``lifespan()`` between :meth:`start` and team start so
        agents that depend on MCP tools get them on first load. Without this,
        :meth:`start` only *spawns* runner tasks — they may still be doing
        ``session.initialize()`` when the team builds its agents.
        """
        events = [r.ready for r in self._runners.values()]
        if not events:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*(e.wait() for e in events)),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            pending = [
                n for n, r in self._runners.items() if r.status.state == "starting"
            ]
            logger.warning(
                "mcp_wait_until_ready_timeout pending={} timeout_s={}",
                pending,
                timeout,
            )

    async def stop(self) -> None:
        """Signal all runners to shut down and await their exit."""
        async with self._lock:
            if not self._started:
                return
            for runner in self._runners.values():
                runner.shutdown.set()
            tasks = [
                r.task
                for r in self._runners.values()
                if r.task is not None and not r.task.done()
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._runners.clear()
            self._started = False
            logger.info("mcp_manager_stopped")

    # ── Public read API ───────────────────────────────────────────────────

    def get_tools_dict(self) -> dict[str, Tool]:
        """Return ``{tool_name: Tool}`` for every healthy server's tools."""
        result: dict[str, Tool] = {}
        for runner in self._runners.values():
            if runner.status.state != "ready":
                continue
            for t in runner.tools:
                result[t.name] = t
        return result

    def server_names(self) -> list[str]:
        """Return all configured server names (any state, enabled or not)."""
        return list(self._runners.keys())

    def get_tools_for_server(self, name: str) -> list[Tool] | None:
        """Return the tool list for a single server.

        - ``None`` if the server is not configured (caller treats as error).
        - ``[]`` if the server is configured but not ready (disabled, starting,
          errored). The agent loads, just without these tools — matches the
          existing "graceful degradation" model in :meth:`get_tools_dict`.
        """
        runner = self._runners.get(name)
        if runner is None:
            return None
        if runner.status.state != "ready":
            return []
        return list(runner.tools)

    def list_status(self) -> list[MCPServerStatus]:
        """Return a snapshot of every configured server's status."""
        return [r.status for r in self._runners.values()]

    def get_status(self, name: str) -> MCPServerStatus | None:
        runner = self._runners.get(name)
        return runner.status if runner else None

    # ── Public mutation API (used by /api/mcp routes) ────────────────────

    async def restart_server(self, name: str) -> MCPServerStatus:
        """Restart a single server. The new config is read from disk.

        Raises ``KeyError`` if ``name`` is not in the current config file.
        """
        cfg = load_config()
        if name not in cfg.servers:
            raise KeyError(name)

        async with self._lock:
            await self._stop_runner(name)
            server_cfg = cfg.servers[name]
            if not server_cfg.enabled:
                self._runners[name] = self._make_disabled_runner(name, server_cfg)
            else:
                await self._spawn_runner(name, server_cfg)

        runner = self._runners[name]
        if runner.status.state != "stopped":
            try:
                await asyncio.wait_for(runner.ready.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning("mcp_restart_timeout server={}", name)
        return runner.status

    async def reload_from_config(self) -> None:
        """Stop all runners and restart from the current config file.

        Done under a single lock so other callers cannot observe an empty
        ``_runners`` dict between the teardown and the respawn.
        """
        async with self._lock:
            for runner in self._runners.values():
                runner.shutdown.set()
            tasks = [
                r.task
                for r in self._runners.values()
                if r.task is not None and not r.task.done()
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._runners.clear()
            self._started = False
            await self._start_locked()

    async def remove_runner(self, name: str) -> None:
        """Tear down ``name``'s runner if present (no-op if absent)."""
        async with self._lock:
            await self._stop_runner(name)
            self._runners.pop(name, None)

    # ── Internals ─────────────────────────────────────────────────────────

    def _make_disabled_runner(
        self, name: str, server_cfg: StdioServerConfig | HttpServerConfig
    ) -> _ServerRunner:
        # Disabled servers carry no task — both events start "set" so any
        # ``ready.wait()`` / ``shutdown.wait()`` returns immediately.
        ready = asyncio.Event()
        ready.set()
        shutdown = asyncio.Event()
        shutdown.set()
        return _ServerRunner(
            shutdown=shutdown,
            ready=ready,
            status=MCPServerStatus(
                name=name,
                transport=server_cfg.transport,
                enabled=False,
                state="stopped",
            ),
        )

    async def _spawn_runner(
        self, name: str, server_cfg: StdioServerConfig | HttpServerConfig
    ) -> None:
        # Two-step construction: register the runner first so ``_run_server``
        # can mutate ``runner.session`` / ``runner.status`` while it executes,
        # then attach the task. ``task`` stays ``Optional`` in the dataclass
        # so this gap is type-safe instead of papered over with type-ignore comments.
        runner = _ServerRunner(
            shutdown=asyncio.Event(),
            ready=asyncio.Event(),
            status=MCPServerStatus(
                name=name,
                transport=server_cfg.transport,
                enabled=True,
                state="starting",
            ),
        )
        self._runners[name] = runner
        runner.task = asyncio.create_task(
            self._run_server(name, server_cfg, runner),
            name=f"mcp-{name}",
        )

    async def _stop_runner(self, name: str) -> None:
        runner = self._runners.get(name)
        if runner is None or runner.task is None:
            # No task means the runner was disabled — nothing to await.
            return
        runner.shutdown.set()
        if not runner.task.done():
            try:
                await asyncio.wait_for(runner.task, timeout=10.0)
            except asyncio.TimeoutError:
                runner.task.cancel()
                try:
                    await runner.task
                except (asyncio.CancelledError, Exception):
                    pass

    async def _run_server(
        self,
        name: str,
        server_cfg: StdioServerConfig | HttpServerConfig,
        runner: _ServerRunner,
    ) -> None:
        """Long-lived task: open the session, list tools, await shutdown."""
        # Imports here so the module is importable without the SDK installed.
        # All three are required for the file to do anything useful, so they
        # share the same prelude rather than scattering one inside an `else`.
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamablehttp_client

        try:
            async with AsyncExitStack() as stack:
                if isinstance(server_cfg, StdioServerConfig):
                    params = StdioServerParameters(
                        command=server_cfg.command,
                        args=list(server_cfg.args),
                        env={**os.environ, **server_cfg.env}
                        if server_cfg.env
                        else None,
                    )
                    read, write = await stack.enter_async_context(stdio_client(params))
                    session = await stack.enter_async_context(
                        ClientSession(read, write)
                    )
                else:
                    transport = await stack.enter_async_context(
                        streamablehttp_client(
                            server_cfg.url, headers=dict(server_cfg.headers) or None
                        )
                    )
                    # streamablehttp_client yields (read, write, get_session_id).
                    read, write = transport[0], transport[1]
                    session = await stack.enter_async_context(
                        ClientSession(read, write)
                    )

                await session.initialize()
                tools_resp = await session.list_tools()

                runner.session = session
                runner.tools = [
                    MCPTool(
                        server_name=name,
                        mcp_tool=t,
                        session_provider=lambda r=runner: r.session,
                    )
                    for t in tools_resp.tools
                ]
                # Mutate the existing status in place rather than rebuilding —
                # ``name``, ``transport``, ``enabled`` are already set correctly
                # by ``_spawn_runner``; only the lifecycle fields move.
                runner.status.state = "ready"
                runner.status.tool_names = [t.name for t in runner.tools]
                runner.status.started_at = datetime.now(UTC).isoformat()
                runner.status.error = None
                runner.ready.set()
                logger.info(
                    "mcp_server_ready name={} transport={} tools={}",
                    name,
                    server_cfg.transport,
                    len(runner.tools),
                )

                # Hold the contexts open until shutdown is requested.
                await runner.shutdown.wait()

                runner.session = None
                logger.info("mcp_server_stopping name={}", name)
        except asyncio.CancelledError:
            runner.status.state = "stopped"
            runner.status.error = None
            runner.ready.set()
            raise
        except Exception as exc:
            logger.error(
                "mcp_server_failed name={} transport={} err={}",
                name,
                server_cfg.transport,
                exc,
            )
            runner.session = None
            runner.tools = []
            runner.status.state = "error"
            runner.status.error = f"{type(exc).__name__}: {exc}"
            runner.status.tool_names = []
            runner.ready.set()


# ── Module-level singleton ─────────────────────────────────────────────────

mcp_manager = MCPManager()
