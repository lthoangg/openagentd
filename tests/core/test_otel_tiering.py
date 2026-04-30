"""Tests for app/core/otel.py — trace-id ratio + error/slow tiering."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from opentelemetry.trace.status import Status, StatusCode

from app.core import otel
from app.core.otel import (
    _FilteringJsonlSpanExporter,
    _trace_passes_ratio,
)


# ── Ratio helper ──────────────────────────────────────────────────────────────


def test_ratio_one_always_passes():
    assert _trace_passes_ratio(0, 1.0) is True
    assert _trace_passes_ratio(2**63, 1.0) is True


def test_ratio_zero_never_passes():
    assert _trace_passes_ratio(0, 0.0) is False
    assert _trace_passes_ratio(2**63, 0.0) is False


def test_ratio_half_splits_roughly():
    # Deterministic over a large sample of synthetic trace IDs spread across
    # the full 64-bit space.
    import random

    rng = random.Random(42)
    ids = [rng.getrandbits(128) for _ in range(2000)]
    passes = sum(_trace_passes_ratio(tid, 0.5) for tid in ids)
    # Half of uniformly-distributed values should pass; tolerate noise.
    assert 800 < passes < 1200


# ── Filtering exporter ────────────────────────────────────────────────────────


def _mk_span(
    *,
    trace_id: int = 0,
    status: StatusCode = StatusCode.OK,
    start_time: int | None = 0,
    end_time: int | None = 1_000_000,  # 1 ms
) -> MagicMock:
    span = MagicMock()
    span.status = Status(status)
    span.start_time = start_time
    span.end_time = end_time
    # Context must carry *real* ints — _span_to_dict uses f-string hex format.
    ctx = MagicMock()
    ctx.trace_id = trace_id
    ctx.span_id = 0xBEEF
    span.get_span_context.return_value = ctx
    span.context = ctx
    span.parent = None
    span.name = "test.span"
    span.kind.name = "INTERNAL"
    span.attributes = {}
    span.events = []
    span.resource = None
    return span


class _StubWriter:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def write(self, obj: dict, ts=None) -> bool:  # noqa: ANN001
        self.records.append(obj)
        return True


def test_error_spans_always_exported(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OTEL_SPAN_SAMPLE_RATIO", "0.0")
    monkeypatch.setenv("OTEL_SLOW_SPAN_MS", "100000")  # 100s — not slow
    writer = _StubWriter()
    exporter = _FilteringJsonlSpanExporter(writer)  # type: ignore[arg-type]
    # trace_id that would be rejected by ratio=0
    span = _mk_span(trace_id=1, status=StatusCode.ERROR)
    exporter.export([span])
    assert len(writer.records) == 1


def test_slow_spans_always_exported(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OTEL_SPAN_SAMPLE_RATIO", "0.0")
    monkeypatch.setenv("OTEL_SLOW_SPAN_MS", "10")  # 10 ms threshold
    writer = _StubWriter()
    exporter = _FilteringJsonlSpanExporter(writer)  # type: ignore[arg-type]
    # Duration: 50 ms = 50_000_000 ns
    span = _mk_span(trace_id=1, start_time=1, end_time=50_000_001)
    exporter.export([span])
    assert len(writer.records) == 1


def test_fast_ok_span_respects_ratio_zero(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OTEL_SPAN_SAMPLE_RATIO", "0.0")
    monkeypatch.setenv("OTEL_SLOW_SPAN_MS", "100000")
    writer = _StubWriter()
    exporter = _FilteringJsonlSpanExporter(writer)  # type: ignore[arg-type]
    span = _mk_span(trace_id=12345, status=StatusCode.OK, end_time=500_000)
    exporter.export([span])
    assert writer.records == []


def test_fast_ok_span_passes_ratio_one(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OTEL_SPAN_SAMPLE_RATIO", "1.0")
    monkeypatch.setenv("OTEL_SLOW_SPAN_MS", "100000")
    writer = _StubWriter()
    exporter = _FilteringJsonlSpanExporter(writer)  # type: ignore[arg-type]
    span = _mk_span(trace_id=12345, status=StatusCode.OK, end_time=500_000)
    exporter.export([span])
    assert len(writer.records) == 1


def test_invalid_sample_ratio_defaults_to_one(monkeypatch: pytest.MonkeyPatch):
    """Invalid env value falls back to the 1.0 default — keep-everything for
    on-machine single-user systems.  Users opt into sampling by setting a
    valid float < 1.0, not by accidentally typo-ing it.
    """
    monkeypatch.setenv("OTEL_SPAN_SAMPLE_RATIO", "not-a-number")
    assert otel._sample_ratio() == 1.0


def test_sample_ratio_clamped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OTEL_SPAN_SAMPLE_RATIO", "9.0")
    assert otel._sample_ratio() == 1.0
    monkeypatch.setenv("OTEL_SPAN_SAMPLE_RATIO", "-0.5")
    assert otel._sample_ratio() == 0.0


def test_slow_threshold_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OTEL_SLOW_SPAN_MS", "250")
    assert otel._slow_span_threshold_ns() == 250_000_000


def test_slow_threshold_invalid_env_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OTEL_SLOW_SPAN_MS", "abc")
    assert otel._slow_span_threshold_ns() == 1_000_000_000


# ── Setup idempotent ──────────────────────────────────────────────────────────


def test_setup_otel_idempotent(tmp_path, monkeypatch: pytest.MonkeyPatch):
    # Reset singletons before the test (module may already be set up from
    # the app import chain).
    otel._tracer_provider = None
    otel._meter_provider = None
    if otel._span_writer is not None:
        otel._span_writer.close()
        otel._span_writer = None
    if otel._metric_writer is not None:
        otel._metric_writer.close()
        otel._metric_writer = None
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    try:
        otel.setup_otel(service_name="test", otel_dir=tmp_path)
        first = otel._tracer_provider
        otel.setup_otel(service_name="test", otel_dir=tmp_path)
        assert otel._tracer_provider is first
    finally:
        otel.shutdown_otel()
