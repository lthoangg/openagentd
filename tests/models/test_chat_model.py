"""Tests for app/models/chat.py — TZDateTime type decorator."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.models.chat import TZDateTime


@pytest.fixture
def tz_type():
    return TZDateTime()


@pytest.fixture
def dialect():
    return MagicMock()


# ---------------------------------------------------------------------------
# process_result_value — None path (line 37)
# ---------------------------------------------------------------------------


def test_process_result_value_none_returns_none(tz_type, dialect):
    """When value is None, process_result_value returns None."""
    result = tz_type.process_result_value(None, dialect)
    assert result is None


# ---------------------------------------------------------------------------
# process_result_value — naive datetime path (line 39-40)
# ---------------------------------------------------------------------------


def test_process_result_value_naive_datetime_gets_utc(tz_type, dialect):
    """Naive datetime (no tzinfo) gets UTC timezone attached."""
    naive = datetime(2024, 6, 15, 12, 0, 0)  # no tzinfo
    result = tz_type.process_result_value(naive, dialect)
    assert result is not None
    assert result.tzinfo == timezone.utc
    assert result.year == 2024
    assert result.hour == 12


# ---------------------------------------------------------------------------
# process_result_value — aware datetime path (line 40, return value)
# ---------------------------------------------------------------------------


def test_process_result_value_aware_datetime_returned_unchanged(tz_type, dialect):
    """Timezone-aware datetime is returned as-is."""
    aware = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    result = tz_type.process_result_value(aware, dialect)
    assert result is aware
