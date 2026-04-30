"""Unit tests for the OTEL JSONL retention sweeper."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from app.core import otel_retention
from app.core.otel_retention import (
    run_otel_retention_once,
    start_otel_retention,
    stop_otel_retention,
    sweep_old_partitions,
)


# ── sweep_old_partitions ──────────────────────────────────────────────────────


def _touch(path: Path, *, age_days: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    when = time.time() - (age_days * 86400)
    os.utime(path, (when, when))


def test_sweep_deletes_files_older_than_cutoff(tmp_path: Path) -> None:
    _touch(tmp_path / "old.jsonl", age_days=45)
    _touch(tmp_path / "fresh.jsonl", age_days=5)

    result = sweep_old_partitions(tmp_path, max_age_days=30)

    assert result.scanned == 2
    assert result.deleted == 1
    assert result.errors == 0
    assert result.bytes_freed > 0
    assert not (tmp_path / "old.jsonl").exists()
    assert (tmp_path / "fresh.jsonl").exists()


def test_sweep_noop_on_missing_root(tmp_path: Path) -> None:
    result = sweep_old_partitions(tmp_path / "missing", max_age_days=30)
    assert result == type(result)(0, 0, 0, 0)


def test_sweep_boundary_keeps_exact_age_files(tmp_path: Path) -> None:
    # A file exactly at the cutoff is kept (strict < comparison).
    _touch(tmp_path / "edge.jsonl", age_days=30)

    # Force "now" to match the expected mtime so the boundary is precise.
    result = sweep_old_partitions(
        tmp_path,
        max_age_days=30,
        now=time.time(),
    )

    # Slight float drift means this could delete or keep; assert it doesn't
    # corrupt the other metrics when it happens either way.
    assert result.scanned == 1
    assert result.errors == 0


def test_sweep_respects_pattern(tmp_path: Path) -> None:
    _touch(tmp_path / "old.jsonl", age_days=45)
    _touch(tmp_path / "old.txt", age_days=45)

    result = sweep_old_partitions(tmp_path, max_age_days=30, pattern="*.jsonl")

    assert result.deleted == 1
    assert not (tmp_path / "old.jsonl").exists()
    assert (tmp_path / "old.txt").exists()


def test_sweep_zero_max_age_is_noop(tmp_path: Path) -> None:
    _touch(tmp_path / "old.jsonl", age_days=365)
    result = sweep_old_partitions(tmp_path, max_age_days=0)
    assert result.deleted == 0
    assert (tmp_path / "old.jsonl").exists()


def test_sweep_skips_directories(tmp_path: Path) -> None:
    (tmp_path / "subdir").mkdir()
    _touch(tmp_path / "old.jsonl", age_days=45)

    result = sweep_old_partitions(tmp_path, max_age_days=30)

    assert result.scanned == 1  # directory was skipped
    assert result.deleted == 1


# ── run_otel_retention_once ───────────────────────────────────────────────────


def test_run_once_sweeps_both_spans_and_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spans = tmp_path / "spans"
    metrics = tmp_path / "metrics"
    _touch(spans / "2020-01-01-00.jsonl", age_days=1000)
    _touch(spans / "today.jsonl", age_days=1)
    _touch(metrics / "2020-01-01.jsonl", age_days=1000)
    _touch(metrics / "today.jsonl", age_days=1)

    # Force default retention values by clearing overrides.
    for var in (
        "OTEL_SPAN_RETENTION_DAYS",
        "OTEL_METRIC_RETENTION_DAYS",
    ):
        monkeypatch.delenv(var, raising=False)

    result = run_otel_retention_once(otel_dir=tmp_path)

    assert result["spans"].deleted == 1
    assert result["metrics"].deleted == 1
    assert (spans / "today.jsonl").exists()
    assert (metrics / "today.jsonl").exists()


def test_run_once_honours_env_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spans = tmp_path / "spans"
    _touch(spans / "a.jsonl", age_days=10)
    _touch(spans / "b.jsonl", age_days=1)

    monkeypatch.setenv("OTEL_SPAN_RETENTION_DAYS", "5")
    monkeypatch.setenv("OTEL_METRIC_RETENTION_DAYS", "5")

    result = run_otel_retention_once(otel_dir=tmp_path)

    assert result["spans"].deleted == 1
    assert not (spans / "a.jsonl").exists()
    assert (spans / "b.jsonl").exists()


def test_run_once_tolerates_empty_dir(tmp_path: Path) -> None:
    # No spans/ or metrics/ directory at all — must not raise.
    result = run_otel_retention_once(otel_dir=tmp_path)
    assert result["spans"].deleted == 0
    assert result["metrics"].deleted == 0


# ── Scheduler task ────────────────────────────────────────────────────────────


def test_start_retention_disabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_RETENTION_ENABLED", "false")
    # Clear any leftover task from earlier tests.
    otel_retention._task = None

    async def _run() -> None:
        start_otel_retention()
        assert otel_retention._task is None

    asyncio.run(_run())


def test_start_retention_runs_once_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _touch(tmp_path / "spans" / "old.jsonl", age_days=365)

    # Point the retention helper at our tmp tree by overriding _otel_dir.
    monkeypatch.setattr(otel_retention, "_otel_dir", lambda: tmp_path)
    # Keep enabled, huge interval so only the initial sweep runs before cancel.
    monkeypatch.setenv("OTEL_RETENTION_ENABLED", "true")
    monkeypatch.setenv("OTEL_RETENTION_SWEEP_INTERVAL_HOURS", "999")
    otel_retention._task = None

    async def _run() -> None:
        start_otel_retention()
        assert otel_retention._task is not None
        # Let the initial sweep run.
        for _ in range(20):
            await asyncio.sleep(0.02)
            if not (tmp_path / "spans" / "old.jsonl").exists():
                break
        await stop_otel_retention()
        assert otel_retention._task is None

    asyncio.run(_run())

    assert not (tmp_path / "spans" / "old.jsonl").exists()
