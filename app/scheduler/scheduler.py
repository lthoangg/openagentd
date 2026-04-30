"""TaskScheduler — asyncio-based scheduled task engine.

Manages a set of :class:`~app.scheduler.models.ScheduledTask` rows, each
backed by a long-running ``asyncio.Task`` that sleeps until ``next_fire_at``
and then dispatches the configured prompt to the agent team.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid5, NAMESPACE_URL

from loguru import logger
from sqlmodel import select

from app.core.db import DbFactory
from app.scheduler.cron import next_fire
from app.scheduler.models import ScheduledTask

if TYPE_CHECKING:
    from app.scheduler.schemas import ScheduledTaskCreate, ScheduledTaskUpdate

_utc = timezone.utc


class AgentNotInTeamError(Exception):
    """Raised when the requested agent does not exist in the current team."""


class TaskNotFoundError(Exception):
    """Raised when a scheduled task lookup by id has no matching row."""


def _require_agent_in_team(agent_name: str) -> None:
    """Raise :exc:`AgentNotInTeamError` if *agent_name* is not in the current team."""
    # TODO: ``app.services.team_manager`` imports from ``app.scheduler`` indirectly,
    # so a top-level import here would cycle.  Resolve by extracting the
    # team-membership predicate into a leaf module (e.g. ``app.team.lookup``) so
    # both layers can import it without going through ``team_manager``.
    from app.services import team_manager

    team = team_manager.current_team()
    if team is None:
        raise AgentNotInTeamError("No team configured.")
    members = {team.lead.name} | set(team.members.keys())
    if agent_name not in members:
        raise AgentNotInTeamError(
            f"Agent '{agent_name}' not found in the current team. "
            f"Available: {sorted(members)}"
        )


class TaskScheduler:
    """Lifecycle manager for scheduled tasks.

    Instantiate once at module level and call :meth:`start` / :meth:`stop`
    from the FastAPI lifespan.
    """

    def __init__(self, db_factory: DbFactory) -> None:
        self._db = db_factory
        # task_id → running asyncio.Task
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Load all enabled tasks from DB and start their timer loops."""
        async with self._db() as session:
            result = await session.exec(
                select(ScheduledTask).where(ScheduledTask.enabled == True)  # noqa: E712
            )
            tasks = result.all()

        now = datetime.now(_utc)
        for task in tasks:
            # One-shot "at" tasks whose fire time is in the past and haven't
            # run yet should fire immediately on startup.
            if (
                task.schedule_type == "at"
                and task.at_datetime is not None
                and task.run_count == 0
                and task.at_datetime <= now
            ):
                asyncio.create_task(self._fire_task(task))
            else:
                self._start_timer(task)

        logger.info("scheduler_started tasks={}", len(tasks))

    async def stop(self) -> None:
        """Cancel all running timer tasks."""
        for t in list(self._tasks.values()):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        logger.info("scheduler_stopped")

    # ── Public API ────────────────────────────────────────────────────────────

    async def add(self, task: ScheduledTask) -> ScheduledTask:
        """Persist *task* to DB and start its timer."""
        task.next_fire_at = next_fire(
            task.schedule_type,
            cron_expression=task.cron_expression,
            every_seconds=task.every_seconds,
            at_datetime=task.at_datetime,
            timezone=task.timezone,
            run_count=task.run_count,
        )
        async with self._db() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)

        if task.enabled:
            self._start_timer(task)
        return task

    async def create(self, body: "ScheduledTaskCreate") -> ScheduledTask:
        """Validate *body*, build a ``ScheduledTask``, persist, and start timer.

        Raises:
            AgentNotInTeamError: If ``body.agent`` is not in the current team.
            sqlalchemy.exc.IntegrityError: On duplicate task name.
        """
        _require_agent_in_team(body.agent)

        task = ScheduledTask(
            name=body.name,
            agent=body.agent,
            schedule_type=body.schedule_type,
            at_datetime=body.at_datetime,
            every_seconds=body.every_seconds,
            cron_expression=body.cron_expression,
            timezone=body.timezone,
            prompt=body.prompt,
            session_id=body.session_id,
            enabled=body.enabled,
        )
        return await self.add(task)

    async def apply_update(
        self, task_id: UUID, body: "ScheduledTaskUpdate"
    ) -> ScheduledTask:
        """Apply a partial update from *body* onto an existing task.

        Validates agent membership if ``body.agent`` is set.

        Raises:
            TaskNotFoundError: If *task_id* does not exist.
            AgentNotInTeamError: If ``body.agent`` is not in the current team.
        """
        task = await self.get_task(task_id)
        if task is None:
            raise TaskNotFoundError(str(task_id))

        if body.agent is not None:
            _require_agent_in_team(body.agent)
            task.agent = body.agent

        if body.schedule_type is not None:
            task.schedule_type = body.schedule_type
        if body.at_datetime is not None:
            task.at_datetime = body.at_datetime
        if body.every_seconds is not None:
            task.every_seconds = body.every_seconds
        if body.cron_expression is not None:
            task.cron_expression = body.cron_expression
        if body.timezone is not None:
            task.timezone = body.timezone
        if body.prompt is not None:
            task.prompt = body.prompt
        if body.session_id is not None:
            task.session_id = body.session_id
        if body.enabled is not None:
            task.enabled = body.enabled

        return await self.update(task)

    async def remove(self, task_id: UUID) -> None:
        """Cancel timer and delete *task_id* from DB."""
        self._cancel_timer(task_id)
        async with self._db() as session:
            result = await session.exec(
                select(ScheduledTask).where(ScheduledTask.id == task_id)
            )
            task = result.first()
            if task is not None:
                await session.delete(task)
                await session.commit()

    async def update(self, task: ScheduledTask) -> ScheduledTask:
        """Persist updated *task* and restart/cancel its timer."""
        self._cancel_timer(task.id)
        task.next_fire_at = next_fire(
            task.schedule_type,
            cron_expression=task.cron_expression,
            every_seconds=task.every_seconds,
            at_datetime=task.at_datetime,
            timezone=task.timezone,
            run_count=task.run_count,
        )
        async with self._db() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)

        if task.enabled:
            self._start_timer(task)
        return task

    async def pause(self, task_id: UUID) -> ScheduledTask:
        """Disable task and cancel its timer."""
        self._cancel_timer(task_id)
        async with self._db() as session:
            result = await session.exec(
                select(ScheduledTask).where(ScheduledTask.id == task_id)
            )
            task = result.one()
            task.enabled = False
            task.status = "paused"
            session.add(task)
            await session.commit()
            await session.refresh(task)
        return task

    async def resume(self, task_id: UUID) -> ScheduledTask:
        """Re-enable task, recompute next_fire_at, and start timer."""
        async with self._db() as session:
            result = await session.exec(
                select(ScheduledTask).where(ScheduledTask.id == task_id)
            )
            task = result.one()
            task.enabled = True
            task.status = "pending"
            task.next_fire_at = next_fire(
                task.schedule_type,
                cron_expression=task.cron_expression,
                every_seconds=task.every_seconds,
                at_datetime=task.at_datetime,
                timezone=task.timezone,
                run_count=task.run_count,
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)

        self._start_timer(task)
        return task

    async def trigger(self, task_id: UUID) -> None:
        """Fire task immediately without affecting the schedule."""
        async with self._db() as session:
            result = await session.exec(
                select(ScheduledTask).where(ScheduledTask.id == task_id)
            )
            task = result.one()
        asyncio.create_task(self._fire_task(task))

    async def list_tasks(self) -> list[ScheduledTask]:
        async with self._db() as session:
            result = await session.exec(select(ScheduledTask))
            return list(result.all())

    async def get_task(self, task_id: UUID) -> ScheduledTask | None:
        async with self._db() as session:
            result = await session.exec(
                select(ScheduledTask).where(ScheduledTask.id == task_id)
            )
            return result.first()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _start_timer(self, task: ScheduledTask) -> None:
        """Spawn an asyncio task for *task*'s timer loop."""
        self._cancel_timer(task.id)
        t = asyncio.create_task(self._timer_loop(task), name=f"scheduler:{task.name}")
        self._tasks[task.id] = t

    def _cancel_timer(self, task_id: UUID) -> None:
        existing = self._tasks.pop(task_id, None)
        if existing is not None:
            existing.cancel()

    async def _timer_loop(self, task: ScheduledTask) -> None:
        """Sleep until next_fire_at, fire, repeat (or exit for one-shots)."""
        while True:
            # Recompute next fire from current state
            nxt = next_fire(
                task.schedule_type,
                cron_expression=task.cron_expression,
                every_seconds=task.every_seconds,
                at_datetime=task.at_datetime,
                timezone=task.timezone,
                run_count=task.run_count,
            )
            if nxt is None:
                # Schedule exhausted (e.g. "at" already ran)
                break

            now = datetime.now(_utc)
            delay = (nxt - now).total_seconds()
            if delay > 0:
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    return

            await self._fire_task(task)

            # Reload task state from DB so run_count / status are fresh
            async with self._db() as session:
                result = await session.exec(
                    select(ScheduledTask).where(ScheduledTask.id == task.id)
                )
                fresh = result.first()
            if fresh is None:
                break
            task = fresh

            # One-shot "at" tasks exit after firing
            if task.schedule_type == "at":
                break

        # Remove ourselves from the tracking dict
        self._tasks.pop(task.id, None)

    async def _fire_task(self, task: ScheduledTask) -> None:
        """Execute one scheduled firing of *task*."""
        from app.services import team_manager
        from app.services.agent_service import NoTeamConfigured, dispatch_user_message

        now = datetime.now(_utc)

        # 1. Mark running
        async with self._db() as session:
            result = await session.exec(
                select(ScheduledTask).where(ScheduledTask.id == task.id)
            )
            db_task = result.first()
            if db_task is None:
                return
            db_task.status = "running"
            db_task.last_run_at = now
            session.add(db_task)
            await session.commit()

        # 2. Resolve session_id
        # "auto" → deterministic uuid5 derived from the task name so the same
        # persistent session is reused across every firing, and it is always a
        # valid UUID (required by handle_user_message / ChatSession PK).
        raw_sid = task.session_id
        if raw_sid is None:
            resolved_sid: str | None = None  # dispatch_user_message will mint one
        elif raw_sid == "auto":
            resolved_sid = str(uuid5(NAMESPACE_URL, f"scheduler:{task.name}"))
        else:
            resolved_sid = raw_sid

        # 3. Dispatch
        error: str | None = None
        fired_sid: str | None = None
        try:
            team = team_manager.current_team()
            if team is None:
                raise NoTeamConfigured("No team configured.")
            fired_sid, _ = await dispatch_user_message(
                team,
                content=f"[Scheduled Task: {task.name}]\n{task.prompt}",
                session_id=resolved_sid,
            )
        except NoTeamConfigured:
            error = "No team configured"
            logger.warning("scheduler_no_team task_id={} name={}", task.id, task.name)
        except Exception as exc:
            error = str(exc)
            logger.error(
                "scheduler_fire_error task_id={} name={} error={}",
                task.id,
                task.name,
                exc,
            )

        # 3b. Stamp the chat session so it's identifiable as scheduler-created.
        # fired_sid is always a valid UUID string at this point:
        #   None     → dispatch_user_message mints a uuid7
        #   "auto"   → resolved to uuid5(NAMESPACE_URL, "scheduler:<name>") above
        #   explicit → caller-supplied UUID string passed through unchanged
        if fired_sid and not error:
            from app.models.chat import ChatSession

            try:
                async with self._db() as db:
                    chat_row = await db.get(ChatSession, UUID(fired_sid))
                    if chat_row is not None:
                        chat_row.scheduled_task_name = task.name
                        db.add(chat_row)
                        await db.commit()
            except Exception as stamp_exc:
                logger.warning(
                    "scheduler_stamp_failed task_id={} sid={} error={}",
                    task.id,
                    fired_sid,
                    stamp_exc,
                )

        # 4. Update stats
        nxt = next_fire(
            task.schedule_type,
            cron_expression=task.cron_expression,
            every_seconds=task.every_seconds,
            at_datetime=task.at_datetime,
            timezone=task.timezone,
            after=datetime.now(_utc),
            run_count=task.run_count + 1,
        )
        async with self._db() as session:
            result = await session.exec(
                select(ScheduledTask).where(ScheduledTask.id == task.id)
            )
            db_task = result.first()
            if db_task is None:
                return
            db_task.run_count += 1
            db_task.last_error = error
            db_task.next_fire_at = nxt
            if error:
                db_task.status = "failed"
            elif task.schedule_type == "at":
                db_task.status = "completed"
            else:
                db_task.status = "pending"
            session.add(db_task)
            await session.commit()

        logger.info(
            "scheduler_fired task_id={} name={} run_count={} error={}",
            task.id,
            task.name,
            task.run_count + 1,
            error,
        )


# ── Module-level singleton ────────────────────────────────────────────────────

from app.core.db import async_session_factory  # noqa: E402

task_scheduler = TaskScheduler(db_factory=async_session_factory)
