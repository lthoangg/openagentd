"""Thin next-fire-time calculator.

Wraps ``croniter`` for cron expressions and handles the simpler
"at" (one-shot) and "every" (interval) schedule types.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def next_fire(
    schedule_type: str,
    *,
    cron_expression: str | None,
    every_seconds: int | None,
    at_datetime: datetime | None,
    timezone: str,
    after: datetime | None = None,
    run_count: int = 0,
) -> datetime | None:
    """Compute the next fire time.

    Returns ``None`` if the schedule is exhausted (e.g. "at" already ran).

    Parameters
    ----------
    schedule_type:
        One of ``"at"``, ``"every"``, ``"cron"``.
    cron_expression:
        5-field cron string (required when ``schedule_type == "cron"``).
    every_seconds:
        Interval in seconds (required when ``schedule_type == "every"``).
    at_datetime:
        One-shot UTC datetime (required when ``schedule_type == "at"``).
    timezone:
        IANA timezone name used as the base for cron evaluation.
    after:
        Compute the next fire *after* this moment.  Defaults to ``now(UTC)``.
    run_count:
        How many times the task has already fired.  Used to determine
        whether a one-shot "at" task is exhausted.
    """
    now = after or datetime.now(tz=_utc)

    if schedule_type == "at":
        if run_count > 0 or at_datetime is None:
            return None
        dt = _ensure_utc(at_datetime)
        return dt

    if schedule_type == "every":
        if every_seconds is None or every_seconds <= 0:
            return None
        return now + timedelta(seconds=every_seconds)

    if schedule_type == "cron":
        if not cron_expression:
            return None
        try:
            tz = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            tz = _utc_zi
        from croniter import croniter

        base = now.astimezone(tz)
        it = croniter(cron_expression, base)
        nxt: datetime = it.get_next(datetime)
        # croniter may return naive or tz-aware depending on version; normalise.
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=tz)
        return nxt.astimezone(_utc)

    return None


def validate_cron(expression: str) -> bool:
    """Return ``True`` if *expression* is a valid 5-field cron string."""
    try:
        from croniter import croniter

        return croniter.is_valid(expression)
    except Exception:
        return False


# ── Helpers ──────────────────────────────────────────────────────────────────

_utc = timezone.utc
_utc_zi = ZoneInfo("UTC")


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_utc)
    return dt.astimezone(_utc)
