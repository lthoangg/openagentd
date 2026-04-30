"""Tests for app/scheduler/cron.py — next_fire + validate_cron."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.scheduler.cron import next_fire, validate_cron


_UTC = timezone.utc


# ---------------------------------------------------------------------------
# next_fire — schedule_type == "at"
# ---------------------------------------------------------------------------


class TestNextFireAt:
    def test_returns_at_datetime_when_run_count_zero(self):
        target = datetime(2030, 1, 1, 12, 0, tzinfo=_UTC)
        result = next_fire(
            "at",
            cron_expression=None,
            every_seconds=None,
            at_datetime=target,
            timezone="UTC",
            run_count=0,
        )
        assert result == target

    def test_returns_none_when_already_run(self):
        target = datetime(2030, 1, 1, 12, 0, tzinfo=_UTC)
        result = next_fire(
            "at",
            cron_expression=None,
            every_seconds=None,
            at_datetime=target,
            timezone="UTC",
            run_count=1,
        )
        assert result is None

    def test_returns_none_when_at_datetime_missing(self):
        result = next_fire(
            "at",
            cron_expression=None,
            every_seconds=None,
            at_datetime=None,
            timezone="UTC",
        )
        assert result is None

    def test_naive_datetime_treated_as_utc(self):
        naive = datetime(2030, 1, 1, 12, 0)  # no tzinfo
        result = next_fire(
            "at",
            cron_expression=None,
            every_seconds=None,
            at_datetime=naive,
            timezone="UTC",
        )
        assert result is not None
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)

    def test_aware_non_utc_datetime_normalised_to_utc(self):
        # 12:00 in Asia/Tokyo (UTC+9) → 03:00 UTC
        tokyo = ZoneInfo("Asia/Tokyo")
        target = datetime(2030, 1, 1, 12, 0, tzinfo=tokyo)
        result = next_fire(
            "at",
            cron_expression=None,
            every_seconds=None,
            at_datetime=target,
            timezone="UTC",
        )
        assert result == datetime(2030, 1, 1, 3, 0, tzinfo=_UTC)


# ---------------------------------------------------------------------------
# next_fire — schedule_type == "every"
# ---------------------------------------------------------------------------


class TestNextFireEvery:
    def test_returns_now_plus_interval(self):
        after = datetime(2030, 1, 1, 12, 0, tzinfo=_UTC)
        result = next_fire(
            "every",
            cron_expression=None,
            every_seconds=60,
            at_datetime=None,
            timezone="UTC",
            after=after,
        )
        assert result == after + timedelta(seconds=60)

    def test_default_after_is_now(self):
        before = datetime.now(_UTC)
        result = next_fire(
            "every",
            cron_expression=None,
            every_seconds=30,
            at_datetime=None,
            timezone="UTC",
        )
        after = datetime.now(_UTC)
        assert result is not None
        # Result should be ~30 s in the future, between (before + 30) and (after + 30).
        assert before + timedelta(seconds=30) <= result <= after + timedelta(seconds=30)

    def test_returns_none_when_every_seconds_missing(self):
        result = next_fire(
            "every",
            cron_expression=None,
            every_seconds=None,
            at_datetime=None,
            timezone="UTC",
        )
        assert result is None

    def test_returns_none_when_every_seconds_zero(self):
        result = next_fire(
            "every",
            cron_expression=None,
            every_seconds=0,
            at_datetime=None,
            timezone="UTC",
        )
        assert result is None

    def test_returns_none_when_every_seconds_negative(self):
        result = next_fire(
            "every",
            cron_expression=None,
            every_seconds=-5,
            at_datetime=None,
            timezone="UTC",
        )
        assert result is None


# ---------------------------------------------------------------------------
# next_fire — schedule_type == "cron"
# ---------------------------------------------------------------------------


class TestNextFireCron:
    def test_every_minute_advances_one_minute(self):
        after = datetime(2030, 1, 1, 12, 0, 30, tzinfo=_UTC)
        result = next_fire(
            "cron",
            cron_expression="* * * * *",
            every_seconds=None,
            at_datetime=None,
            timezone="UTC",
            after=after,
        )
        assert result == datetime(2030, 1, 1, 12, 1, tzinfo=_UTC)

    def test_daily_midnight_advances_to_next_day(self):
        after = datetime(2030, 1, 1, 13, 0, tzinfo=_UTC)
        result = next_fire(
            "cron",
            cron_expression="0 0 * * *",
            every_seconds=None,
            at_datetime=None,
            timezone="UTC",
            after=after,
        )
        assert result == datetime(2030, 1, 2, 0, 0, tzinfo=_UTC)

    def test_timezone_affects_cron_evaluation(self):
        """`0 9 * * *` in Asia/Tokyo → 09:00 JST = 00:00 UTC."""
        # After 23:00 UTC on day 1 → next 09:00 JST is day 2 (00:00 UTC).
        after = datetime(2030, 1, 1, 23, 0, tzinfo=_UTC)
        result = next_fire(
            "cron",
            cron_expression="0 9 * * *",
            every_seconds=None,
            at_datetime=None,
            timezone="Asia/Tokyo",
            after=after,
        )
        assert result == datetime(2030, 1, 2, 0, 0, tzinfo=_UTC)

    def test_invalid_timezone_falls_back_to_utc(self):
        after = datetime(2030, 1, 1, 12, 0, tzinfo=_UTC)
        result = next_fire(
            "cron",
            cron_expression="0 0 * * *",
            every_seconds=None,
            at_datetime=None,
            timezone="Not/A_Real_Zone",
            after=after,
        )
        # Falls back to UTC, so next 00:00 UTC after 12:00 is the next day.
        assert result == datetime(2030, 1, 2, 0, 0, tzinfo=_UTC)

    def test_returns_none_when_cron_expression_missing(self):
        result = next_fire(
            "cron",
            cron_expression=None,
            every_seconds=None,
            at_datetime=None,
            timezone="UTC",
        )
        assert result is None

    def test_returns_none_when_cron_expression_empty(self):
        result = next_fire(
            "cron",
            cron_expression="",
            every_seconds=None,
            at_datetime=None,
            timezone="UTC",
        )
        assert result is None


# ---------------------------------------------------------------------------
# next_fire — unknown schedule_type
# ---------------------------------------------------------------------------


class TestNextFireUnknown:
    def test_unknown_type_returns_none(self):
        result = next_fire(
            "bogus",
            cron_expression=None,
            every_seconds=None,
            at_datetime=None,
            timezone="UTC",
        )
        assert result is None


# ---------------------------------------------------------------------------
# validate_cron
# ---------------------------------------------------------------------------


class TestValidateCron:
    def test_valid_5_field_expression(self):
        assert validate_cron("0 0 * * *") is True

    def test_valid_every_minute(self):
        assert validate_cron("* * * * *") is True

    def test_valid_with_step_values(self):
        assert validate_cron("*/15 * * * *") is True

    def test_invalid_random_string(self):
        assert validate_cron("not a cron") is False

    def test_invalid_too_few_fields(self):
        assert validate_cron("0 0 *") is False

    def test_invalid_out_of_range_minute(self):
        assert validate_cron("60 0 * * *") is False

    def test_empty_string_invalid(self):
        assert validate_cron("") is False
