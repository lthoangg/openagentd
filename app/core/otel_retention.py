"""Retention sweeper for OTEL JSONL partitions.

Deletes span/metric partition files older than a configured age so local
telemetry storage does not grow unbounded.

Defaults
--------
- Spans:   30 days  (``OTEL_SPAN_RETENTION_DAYS``)
- Metrics: 90 days  (``OTEL_METRIC_RETENTION_DAYS``)
- Sweep every 24 h  (``OTEL_RETENTION_SWEEP_INTERVAL_HOURS``)
- Toggle with      (``OTEL_RETENTION_ENABLED=false`` disables)

Files live under ``{STATE_DIR}/otel/spans/*.jsonl`` and
``{STATE_DIR}/otel/metrics/*.jsonl``.  Age is computed from file
``mtime`` — correct for append-only partitioned writes.

The sweeper is a background asyncio task started in the FastAPI lifespan.
It runs one sweep at startup, then sleeps until the next interval.  Failures
in a single file do not abort the sweep; they are logged and counted.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


# ── Config helpers (env-driven, no Settings dependency) ──────────────────────


def _int_env(name: str, default: int, *, min_value: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    return max(min_value, v)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _span_retention_days() -> int:
    return _int_env("OTEL_SPAN_RETENTION_DAYS", 30, min_value=1)


def _metric_retention_days() -> int:
    return _int_env("OTEL_METRIC_RETENTION_DAYS", 90, min_value=1)


def _sweep_interval_seconds() -> float:
    hours = _int_env("OTEL_RETENTION_SWEEP_INTERVAL_HOURS", 24, min_value=1)
    return float(hours * 3600)


def _retention_enabled() -> bool:
    return _bool_env("OTEL_RETENTION_ENABLED", True)


def _otel_dir() -> Path:
    from app.core.config import settings

    return Path(settings.OPENAGENTD_STATE_DIR) / "otel"


# ── Core sweep ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SweepResult:
    scanned: int
    deleted: int
    errors: int
    bytes_freed: int


def sweep_old_partitions(
    root: Path,
    *,
    max_age_days: int,
    pattern: str = "*.jsonl",
    now: float | None = None,
) -> SweepResult:
    """Delete files under ``root`` matching ``pattern`` older than ``max_age_days``.

    Non-existent roots return an empty result — safe to call before any span
    has been written.  Per-file errors (permission denied, already-removed) are
    counted but never raised; the sweep always completes.

    Age is computed against ``mtime`` so in-flight open files keep their
    current partition-hour mtime and are never prematurely deleted.
    """
    if max_age_days <= 0:
        return SweepResult(0, 0, 0, 0)
    if not root.exists():
        return SweepResult(0, 0, 0, 0)

    cutoff = (now if now is not None else time.time()) - (max_age_days * 86400)
    scanned = 0
    deleted = 0
    errors = 0
    bytes_freed = 0

    for path in root.glob(pattern):
        if not path.is_file():
            continue
        scanned += 1
        try:
            stat = path.stat()
        except OSError:
            errors += 1
            continue
        if stat.st_mtime >= cutoff:
            continue
        try:
            size = stat.st_size
            path.unlink()
        except OSError as exc:
            errors += 1
            logger.warning("otel_retention_unlink_failed path={} error={}", path, exc)
            continue
        deleted += 1
        bytes_freed += size

    return SweepResult(
        scanned=scanned, deleted=deleted, errors=errors, bytes_freed=bytes_freed
    )


def run_otel_retention_once(otel_dir: Path | None = None) -> dict[str, SweepResult]:
    """Run one retention pass over spans and metrics.

    Returns the per-directory ``SweepResult`` so callers (tests, logs, metrics)
    can observe what was removed.
    """
    base = otel_dir or _otel_dir()
    span_days = _span_retention_days()
    metric_days = _metric_retention_days()

    spans_result = sweep_old_partitions(base / "spans", max_age_days=span_days)
    metrics_result = sweep_old_partitions(base / "metrics", max_age_days=metric_days)

    if spans_result.deleted or metrics_result.deleted:
        logger.info(
            "otel_retention_swept spans_deleted={} spans_bytes={} "
            "metrics_deleted={} metrics_bytes={} span_days={} metric_days={}",
            spans_result.deleted,
            spans_result.bytes_freed,
            metrics_result.deleted,
            metrics_result.bytes_freed,
            span_days,
            metric_days,
        )
    else:
        logger.debug(
            "otel_retention_swept nothing_to_delete "
            "spans_scanned={} metrics_scanned={}",
            spans_result.scanned,
            metrics_result.scanned,
        )

    return {"spans": spans_result, "metrics": metrics_result}


# ── Background scheduler ──────────────────────────────────────────────────────


_task: asyncio.Task[None] | None = None


async def _retention_loop() -> None:
    interval = _sweep_interval_seconds()
    # Run one sweep immediately at boot, then on interval.
    while True:
        try:
            await asyncio.to_thread(run_otel_retention_once)
        except Exception as exc:  # noqa: BLE001  never kill the scheduler
            logger.warning("otel_retention_sweep_failed error={}", exc)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise


def start_otel_retention() -> None:
    """Launch the background retention task.  Idempotent."""
    global _task
    if not _retention_enabled():
        logger.info("otel_retention_disabled")
        return
    if _task is not None and not _task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop yet — skip silently; called from non-async context.
        return
    _task = loop.create_task(_retention_loop(), name="otel-retention")
    logger.info(
        "otel_retention_started span_days={} metric_days={} interval_h={}",
        _span_retention_days(),
        _metric_retention_days(),
        int(_sweep_interval_seconds() // 3600),
    )


async def stop_otel_retention() -> None:
    """Cancel the background task, if any."""
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except (asyncio.CancelledError, Exception):
        pass
    _task = None
