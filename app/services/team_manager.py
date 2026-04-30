"""Team lifecycle manager.

Wraps the global ``AgentTeam`` instance.  ``app.api.deps.get_team``
reads ``current_team()`` so route handlers always see the latest value.

Usage::

    await team_manager.start()                       # startup
    await team_manager.stop()                        # shutdown

Live-config refresh — no team reload
------------------------------------

Agents now refresh themselves at the start of their next turn when
their tracked config files (their own ``.md``, ``mcp.json``, referenced
``SKILL.md``) change on disk.  See ``app.agent.loader.stamp_agent_files``
and ``TeamMemberBase._detect_config_drift``.  Production code paths
(``/api/mcp``, ``/api/skills``, ``/api/agents``) therefore do **not**
call :func:`reload`.

:func:`reload` is retained as a legacy admin tool for operational forced
rebuilds and as a hook for tests; do not call it from request handlers.
It rebuilds the entire team — stopping in-flight agents and rotating
session IDs — which is exactly what the live-config mechanism was
introduced to avoid.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from app.agent.loader import load_team_from_dir
from app.core.config import settings

if TYPE_CHECKING:
    from app.agent.mode.team.team import AgentTeam


# ── Diff dataclass ───────────────────────────────────────────────────────────


@dataclass
class TeamDiff:
    """Difference between the previous and new team after a reload."""

    added: list[str]  # agent names added
    removed: list[str]  # agent names removed
    changed: list[str]  # agent names where model / tools / skills changed
    lead: str  # name of the new lead
    members: list[str]  # names of all members (excluding lead)

    def to_dict(self) -> dict:
        return {
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
            "lead": self.lead,
            "members": self.members,
        }


# ── Module-level state ───────────────────────────────────────────────────────

_team: "AgentTeam | None" = None
_lock = asyncio.Lock()


def _resolve_agents_dir() -> Path:
    path = Path(settings.AGENTS_DIR)
    return path if path.is_absolute() else Path.cwd() / path


def current_team() -> "AgentTeam | None":
    return _team


def set_team(team: "AgentTeam | None") -> None:
    """Replace the current team reference without running the lifecycle.

    Intended for tests that need to inject a pre-built ``AgentTeam`` into
    the FastAPI dependency without starting the real team.  Production
    code should use :func:`start` / :func:`reload` / :func:`stop`.
    """
    global _team
    _team = team


# ── Lifecycle ────────────────────────────────────────────────────────────────


async def start() -> "AgentTeam | None":
    """Load and start the team on server startup.  Idempotent."""
    global _team
    async with _lock:
        if _team is not None:
            return _team

        agents_dir = _resolve_agents_dir()
        team = load_team_from_dir(agents_dir)
        if team is None:
            logger.warning("team_manager_no_agents path={}", agents_dir)
            return None

        await team.start()
        _team = team
        logger.info("team_manager_started lead={}", team.lead.name)
        return team


async def stop() -> None:
    """Stop the current team (if any) on server shutdown."""
    global _team
    async with _lock:
        if _team is None:
            return
        try:
            await _team.stop()
        except Exception:
            logger.exception("team_manager_stop_error")
        _team = None


# ── Hot reload ───────────────────────────────────────────────────────────────


def _team_snapshot(team: "AgentTeam") -> dict[str, dict]:
    """Capture per-agent fingerprint used to compute the diff."""
    snapshot: dict[str, dict] = {}
    members = [team.lead, *team.members.values()]
    for m in members:
        agent = m.agent
        snapshot[agent.name] = {
            "description": agent.description or "",
            "model": agent.model_id,
            "tools": sorted(t.name for t in agent._tools.values()),
            "skills": sorted(agent.skills or []),
            "system_prompt": agent.system_prompt,
        }
    return snapshot


def _compute_diff(before: dict[str, dict] | None, team: "AgentTeam") -> TeamDiff:
    after = _team_snapshot(team)
    before = before or {}

    before_names = set(before.keys())
    after_names = set(after.keys())

    added = sorted(after_names - before_names)
    removed = sorted(before_names - after_names)
    changed = sorted(
        name for name in before_names & after_names if before[name] != after[name]
    )

    members = sorted(team.members.keys())
    return TeamDiff(
        added=added,
        removed=removed,
        changed=changed,
        lead=team.lead.name,
        members=members,
    )


async def reload() -> TeamDiff:
    """Rebuild the team from ``AGENTS_DIR`` and atomically swap it in.

    .. warning::
        Legacy admin path.  Calling this stops every agent (cancelling
        any in-flight tool execution, rotating session IDs, emitting a
        premature ``done`` event for the active turn).  Production code
        should rely on the live-config refresh mechanism instead — see
        the module docstring.

    Raises ``ValueError`` (from :func:`load_team_from_dir`) on any validation
    failure — the running team is untouched in that case.
    """
    global _team
    async with _lock:
        agents_dir = _resolve_agents_dir()

        # 1. Build candidate first — throws on validation failure, running
        #    team stays live.
        candidate = load_team_from_dir(agents_dir)
        if candidate is None:
            raise ValueError(
                f"No agents found in '{agents_dir}'. "
                "Create at least one .md file with 'role: lead' before reloading."
            )

        # 2. Snapshot the old team (for diff) and stop it.
        before_snapshot = _team_snapshot(_team) if _team is not None else None
        old_team = _team
        if old_team is not None:
            try:
                await old_team.stop()
            except Exception:
                logger.exception("team_manager_reload_stop_error")

        # 3. Start the new one.  ``app.api.deps.get_team`` will pick it up
        #    via :func:`current_team` on the next request.
        await candidate.start()
        _team = candidate

        diff = _compute_diff(before_snapshot, candidate)
        logger.info(
            "team_manager_reloaded lead={} added={} removed={} changed={}",
            diff.lead,
            diff.added,
            diff.removed,
            diff.changed,
        )
        return diff


# ── Live-config refresh ──────────────────────────────────────────────────────


def refresh_idle_agents(team: "AgentTeam") -> None:
    """Detect and apply config drift for all idle (non-working) agents.

    This is the same mechanism agents use at start-of-turn, hoisted into
    a service function so the ``GET /team/agents`` route can serve fresh
    frontmatter without knowing about ``TeamMemberBase`` internals.

    Working agents are skipped — refreshing them would race ``agent.run()``
    swapping ``self.agent`` mid-execution.

    Errors are swallowed and logged so a single bad agent config never
    breaks the listing endpoint.
    """
    for member in [team.lead, *team.members.values()]:
        if member.state == "working":
            continue
        try:
            member.refresh_if_dirty()
        except Exception as exc:
            logger.warning(
                "team_agents_refresh_failed name={} error={}", member.name, exc
            )


# ── Skill cache invalidation ─────────────────────────────────────────────────


def invalidate_skill_cache() -> None:
    """Clear the ``discover_skills`` lru_cache so the next tool call
    picks up edits to ``{SKILLS_DIR}/*/SKILL.md``.  No team reload needed.
    """
    from app.agent.tools.builtin.skill import _discover_skills_cached

    _discover_skills_cached.cache_clear()
    logger.info("team_manager_skill_cache_invalidated")
