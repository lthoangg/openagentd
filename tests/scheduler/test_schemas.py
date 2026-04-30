"""Tests for app/scheduler/schemas.py — request validators."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.scheduler.schemas import ScheduledTaskCreate, ScheduledTaskUpdate


_UTC = timezone.utc


# ---------------------------------------------------------------------------
# ScheduledTaskCreate — name validation
# ---------------------------------------------------------------------------


class TestNameValidation:
    def test_valid_simple_name(self):
        body = ScheduledTaskCreate(
            name="hello",
            agent="bot",
            schedule_type="every",
            every_seconds=60,
            prompt="hi",
        )
        assert body.name == "hello"

    def test_valid_with_dots_dashes_underscores(self):
        body = ScheduledTaskCreate(
            name="my.task-1_v2",
            agent="bot",
            schedule_type="every",
            every_seconds=60,
            prompt="hi",
        )
        assert body.name == "my.task-1_v2"

    @pytest.mark.parametrize(
        "bad",
        [
            "",  # empty
            ".leading-dot",  # bad first char
            "-leading-dash",
            "_leading-underscore",
            "has space",
            "has/slash",
            "x" * 65,  # too long (> 64)
            "weird!chars",
        ],
    )
    def test_invalid_names_rejected(self, bad):
        with pytest.raises(ValidationError) as excinfo:
            ScheduledTaskCreate(
                name=bad,
                agent="bot",
                schedule_type="every",
                every_seconds=60,
                prompt="hi",
            )
        assert "name must match" in str(excinfo.value)


# ---------------------------------------------------------------------------
# ScheduledTaskCreate — schedule_type "at"
# ---------------------------------------------------------------------------


class TestCreateAt:
    def test_valid_at(self):
        target = datetime(2030, 1, 1, 12, 0, tzinfo=_UTC)
        body = ScheduledTaskCreate(
            name="t1",
            agent="bot",
            schedule_type="at",
            at_datetime=target,
            prompt="hi",
        )
        assert body.at_datetime == target

    def test_at_requires_at_datetime(self):
        with pytest.raises(ValidationError, match="at_datetime is required"):
            ScheduledTaskCreate(
                name="t1",
                agent="bot",
                schedule_type="at",
                prompt="hi",
            )

    def test_at_rejects_every_seconds(self):
        with pytest.raises(ValidationError, match="Only at_datetime"):
            ScheduledTaskCreate(
                name="t1",
                agent="bot",
                schedule_type="at",
                at_datetime=datetime(2030, 1, 1, tzinfo=_UTC),
                every_seconds=60,
                prompt="hi",
            )

    def test_at_rejects_cron_expression(self):
        with pytest.raises(ValidationError, match="Only at_datetime"):
            ScheduledTaskCreate(
                name="t1",
                agent="bot",
                schedule_type="at",
                at_datetime=datetime(2030, 1, 1, tzinfo=_UTC),
                cron_expression="* * * * *",
                prompt="hi",
            )


# ---------------------------------------------------------------------------
# ScheduledTaskCreate — schedule_type "every"
# ---------------------------------------------------------------------------


class TestCreateEvery:
    def test_valid_every(self):
        body = ScheduledTaskCreate(
            name="t",
            agent="bot",
            schedule_type="every",
            every_seconds=300,
            prompt="hi",
        )
        assert body.every_seconds == 300

    def test_every_requires_every_seconds(self):
        with pytest.raises(ValidationError, match="every_seconds is required"):
            ScheduledTaskCreate(
                name="t",
                agent="bot",
                schedule_type="every",
                prompt="hi",
            )

    def test_every_rejects_at_datetime(self):
        with pytest.raises(ValidationError, match="Only every_seconds"):
            ScheduledTaskCreate(
                name="t",
                agent="bot",
                schedule_type="every",
                every_seconds=60,
                at_datetime=datetime(2030, 1, 1, tzinfo=_UTC),
                prompt="hi",
            )

    def test_every_rejects_cron(self):
        with pytest.raises(ValidationError, match="Only every_seconds"):
            ScheduledTaskCreate(
                name="t",
                agent="bot",
                schedule_type="every",
                every_seconds=60,
                cron_expression="* * * * *",
                prompt="hi",
            )

    def test_every_seconds_must_be_positive(self):
        with pytest.raises(ValidationError):
            ScheduledTaskCreate(
                name="t",
                agent="bot",
                schedule_type="every",
                every_seconds=0,
                prompt="hi",
            )


# ---------------------------------------------------------------------------
# ScheduledTaskCreate — schedule_type "cron"
# ---------------------------------------------------------------------------


class TestCreateCron:
    def test_valid_cron(self):
        body = ScheduledTaskCreate(
            name="t",
            agent="bot",
            schedule_type="cron",
            cron_expression="0 0 * * *",
            prompt="hi",
        )
        assert body.cron_expression == "0 0 * * *"

    def test_cron_requires_cron_expression(self):
        with pytest.raises(ValidationError, match="cron_expression is required"):
            ScheduledTaskCreate(
                name="t",
                agent="bot",
                schedule_type="cron",
                prompt="hi",
            )

    def test_cron_rejects_at_datetime(self):
        with pytest.raises(ValidationError, match="Only cron_expression"):
            ScheduledTaskCreate(
                name="t",
                agent="bot",
                schedule_type="cron",
                cron_expression="* * * * *",
                at_datetime=datetime(2030, 1, 1, tzinfo=_UTC),
                prompt="hi",
            )

    def test_cron_rejects_every_seconds(self):
        with pytest.raises(ValidationError, match="Only cron_expression"):
            ScheduledTaskCreate(
                name="t",
                agent="bot",
                schedule_type="cron",
                cron_expression="* * * * *",
                every_seconds=60,
                prompt="hi",
            )

    def test_invalid_cron_expression_rejected(self):
        with pytest.raises(ValidationError, match="Invalid cron expression"):
            ScheduledTaskCreate(
                name="t",
                agent="bot",
                schedule_type="cron",
                cron_expression="not a cron",
                prompt="hi",
            )


# ---------------------------------------------------------------------------
# ScheduledTaskCreate — unknown schedule_type
# ---------------------------------------------------------------------------


class TestCreateUnknown:
    def test_unknown_schedule_type_rejected(self):
        with pytest.raises(ValidationError, match="schedule_type must be"):
            ScheduledTaskCreate(
                name="t",
                agent="bot",
                schedule_type="weekly",
                prompt="hi",
            )


# ---------------------------------------------------------------------------
# ScheduledTaskUpdate — partial validation
# ---------------------------------------------------------------------------


class TestUpdate:
    def test_no_schedule_type_skips_validation(self):
        # Only agent change — schedule fields not validated.
        body = ScheduledTaskUpdate(agent="bot2")
        assert body.agent == "bot2"

    def test_at_in_update_rejects_other_fields(self):
        with pytest.raises(ValidationError, match="Only at_datetime"):
            ScheduledTaskUpdate(
                schedule_type="at",
                at_datetime=datetime(2030, 1, 1, tzinfo=_UTC),
                every_seconds=60,
            )

    def test_every_in_update_rejects_other_fields(self):
        with pytest.raises(ValidationError, match="Only every_seconds"):
            ScheduledTaskUpdate(
                schedule_type="every",
                every_seconds=60,
                cron_expression="* * * * *",
            )

    def test_cron_in_update_rejects_other_fields(self):
        with pytest.raises(ValidationError, match="Only cron_expression"):
            ScheduledTaskUpdate(
                schedule_type="cron",
                cron_expression="* * * * *",
                at_datetime=datetime(2030, 1, 1, tzinfo=_UTC),
            )

    def test_cron_validation_runs_when_expression_present(self):
        with pytest.raises(ValidationError, match="Invalid cron expression"):
            ScheduledTaskUpdate(
                schedule_type="cron",
                cron_expression="bogus",
            )

    def test_cron_without_expression_allowed_for_partial_update(self):
        # schedule_type=cron without cron_expression is permitted on partial
        # updates because the existing row already has a valid expression.
        body = ScheduledTaskUpdate(schedule_type="cron")
        assert body.schedule_type == "cron"

    def test_unknown_schedule_type_rejected(self):
        with pytest.raises(ValidationError, match="schedule_type must be"):
            ScheduledTaskUpdate(schedule_type="yearly")
