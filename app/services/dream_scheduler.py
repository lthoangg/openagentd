"""Dream scheduler — runs dream on a cron schedule.

Reads schedule from ``.openagentd/config/dream.md`` via
:func:`app.services.dream.parse_dream_md`.  Only starts if dream.md
exists and ``enabled: true``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from croniter import croniter
from loguru import logger

from app.core.config import settings

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.db import DbFactory


def _dream_config_path() -> Path:
    return Path(settings.OPENAGENTD_CONFIG_DIR) / "dream.md"


class DreamScheduler:
    """Background scheduler that runs dream on a cron schedule."""

    def __init__(self, db_factory: "DbFactory") -> None:
        self._db_factory = db_factory
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background scheduler task if dream.md is enabled."""
        from app.services.dream import parse_dream_md

        path = _dream_config_path()
        if not path.exists():
            logger.debug("dream_scheduler_disabled no dream.md")
            return

        try:
            cfg = parse_dream_md(path)
        except ValueError as exc:
            logger.warning("dream_scheduler_config_error error={}", exc)
            return

        if not cfg.enabled:
            logger.debug("dream_scheduler_disabled enabled=false")
            return

        logger.info(
            "dream_scheduler_starting schedule={} model={}",
            cfg.schedule,
            cfg.model or "(none — infra-only)",
        )
        self._task = asyncio.create_task(
            self._loop(cfg.schedule), name="dream-scheduler"
        )

    async def stop(self) -> None:
        """Stop the scheduler, cancelling any pending sleep but not a running fire."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("dream_scheduler_stopped")

    async def reload(self) -> None:
        """Reload the scheduler from the current dream.md without interrupting
        an in-progress dream run.

        If the scheduler loop is currently sleeping between fires, the sleep is
        cancelled immediately and the loop exits cleanly.  If a fire() is
        actively running (i.e. the dream agent is synthesising), we wait for it
        to complete before stopping and restarting — so no run is cut short.

        Called by ``PUT /api/dream/config`` so schedule / enabled changes take
        effect immediately without a server restart.
        """
        if self._task is not None and not self._task.done():
            # Signal the loop to stop after the current fire (if any) completes.
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("dream_scheduler_stopped_for_reload")

        await self.start()
        logger.info("dream_scheduler_reloaded")

    async def run_now(self, db: "AsyncSession") -> dict:
        """Run dream immediately (for /api/dream/run)."""
        from app.services.dream import run_dream

        return await run_dream(db)

    async def _loop(self, schedule: str) -> None:
        """Main scheduler loop — sleeps until next cron fire time.

        The sleep is cancellable (so ``reload()`` / ``stop()`` take effect
        quickly), but an active ``_fire()`` call is shielded from cancellation
        so a running dream synthesis is never cut short.  If cancellation
        arrives while firing, the CancelledError is re-raised after the fire
        completes.
        """
        while True:
            try:
                now = datetime.now(timezone.utc)
                cron = croniter(schedule, now)
                next_fire: datetime = cron.get_next(datetime)
                sleep_seconds = (next_fire - now).total_seconds()
                logger.info(
                    "dream_scheduler_next_fire at={} sleep_seconds={:.0f}",
                    next_fire.isoformat(),
                    sleep_seconds,
                )
                await asyncio.sleep(max(sleep_seconds, 0))
            except asyncio.CancelledError:
                # Cancelled during sleep — exit cleanly without firing.
                raise

            # Fire is shielded: cancellation arriving here waits until the
            # dream run finishes, then re-raises so the loop exits.
            cancelled = False
            try:
                await asyncio.shield(self._fire())
            except asyncio.CancelledError:
                cancelled = True
            except Exception as exc:
                logger.error("dream_scheduler_loop_error error={}", exc)
                await asyncio.sleep(60)

            if cancelled:
                raise asyncio.CancelledError

    async def _fire(self) -> None:
        """Execute one dream run."""
        logger.info("dream_scheduler_firing")
        try:
            async with self._db_factory() as db:
                from app.services.dream import run_dream

                result = await run_dream(db)
                logger.info("dream_scheduler_fired result={}", result)
        except Exception as exc:
            logger.error("dream_scheduler_fire_failed error={}", exc)
