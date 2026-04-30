"""Tests for app/api/routes/observability.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.observability import router
from app.services import observability_service
from app.services.observability_service import DuckDBUnavailable


def _write_agent_run(
    tmp_path: Path,
    *,
    trace_id: str = "0x" + "1" * 32,
    run_id: str = "run-1",
) -> None:
    """Write one ``agent_run`` + ``chat`` pair into a fresh hourly file."""
    now_ns = int(datetime.now(timezone.utc).timestamp() * 1e9)
    spans_dir = tmp_path / "otel" / "spans"
    spans_dir.mkdir(parents=True, exist_ok=True)
    key = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    root_id = "0x" + "a" * 16
    root = {
        "name": "agent_run lead",
        "trace_id": trace_id,
        "span_id": root_id,
        "parent_id": None,
        "kind": "INTERNAL",
        "start_time": now_ns - 1_500_000_000,
        "end_time": now_ns,
        "duration_ms": 1500.0,
        "status": "OK",
        "attributes": {
            "gen_ai.agent.name": "lead",
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.conversation.id": "sess-a",
            "run_id": run_id,
            "gen_ai.usage.input_tokens": 1000,
            "gen_ai.usage.output_tokens": 200,
        },
        "events": [],
        "resource": {"service.name": "openagentd"},
    }
    child = {
        "name": "chat gpt-4o",
        "trace_id": trace_id,
        "span_id": "0x" + "b" * 16,
        "parent_id": root_id,
        "kind": "CLIENT",
        "start_time": now_ns - 500_000_000,
        "end_time": now_ns - 100_000_000,
        "duration_ms": 400.0,
        "status": "OK",
        "attributes": {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "gpt-4o",
        },
        "events": [],
        "resource": {"service.name": "openagentd"},
    }
    with (spans_dir / f"{key}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(root) + "\n")
        f.write(json.dumps(child) + "\n")


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/observability")
    return app


def test_returns_empty_payload_when_no_spans(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        observability_service,
        "_spans_dir",
        lambda: tmp_path / "otel" / "spans",
    )
    client = TestClient(_make_app())
    resp = client.get("/api/observability/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["turns"] == 0
    assert body["daily_turns"] == []
    assert "sample_ratio" in body


def test_days_query_param_bounds(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        observability_service,
        "_spans_dir",
        lambda: tmp_path / "otel" / "spans",
    )
    client = TestClient(_make_app())
    # Below min → 422
    assert client.get("/api/observability/summary?days=0").status_code == 422
    # Above max → 422
    assert client.get("/api/observability/summary?days=91").status_code == 422
    # Within range → 200
    assert client.get("/api/observability/summary?days=30").status_code == 200


def test_503_when_duckdb_unavailable(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        observability_service,
        "_spans_dir",
        lambda: tmp_path / "otel" / "spans",
    )

    # Create a span file so the import path is exercised.
    (tmp_path / "otel" / "spans").mkdir(parents=True)
    (tmp_path / "otel" / "spans" / "2026-04-17-14.jsonl").write_text(
        '{"name":"agent_run lead","end_time":1,"start_time":0,'
        '"duration_ms":1.0,"status":"OK","attributes":{}}\n'
    )

    def _boom():
        raise DuckDBUnavailable("go install the [otel] extra")

    monkeypatch.setattr(observability_service, "_try_import_duckdb", _boom)

    client = TestClient(_make_app())
    resp = client.get("/api/observability/summary?days=30")
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["reason"] == "duckdb_unavailable"


# ── /traces ───────────────────────────────────────────────────────────────────


def test_traces_list_returns_empty_when_no_spans(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        observability_service,
        "_spans_dir",
        lambda: tmp_path / "otel" / "spans",
    )
    client = TestClient(_make_app())
    resp = client.get("/api/observability/traces")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"traces": [], "limit": 50, "offset": 0}


def test_traces_list_returns_turn_rows(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        observability_service,
        "_spans_dir",
        lambda: tmp_path / "otel" / "spans",
    )
    _write_agent_run(tmp_path, trace_id="0x" + "1" * 32, run_id="run-1")
    client = TestClient(_make_app())

    resp = client.get("/api/observability/traces?days=7&limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["traces"]) == 1
    row = body["traces"][0]
    assert row["trace_id"] == "0x" + "1" * 32
    assert row["run_id"] == "run-1"
    assert row["agent_name"] == "lead"
    assert row["model"] == "gpt-4o"
    assert row["input_tokens"] == 1000
    assert row["llm_calls"] == 1
    assert row["error"] is False


def test_traces_list_respects_query_bounds(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        observability_service,
        "_spans_dir",
        lambda: tmp_path / "otel" / "spans",
    )
    client = TestClient(_make_app())
    assert client.get("/api/observability/traces?limit=0").status_code == 422
    assert client.get("/api/observability/traces?limit=201").status_code == 422
    assert client.get("/api/observability/traces?offset=-1").status_code == 422


def test_traces_list_503_when_duckdb_unavailable(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        observability_service,
        "_spans_dir",
        lambda: tmp_path / "otel" / "spans",
    )
    _write_agent_run(tmp_path)

    def _boom():
        raise DuckDBUnavailable("install the [otel] extra")

    monkeypatch.setattr(observability_service, "_try_import_duckdb", _boom)

    client = TestClient(_make_app())
    resp = client.get("/api/observability/traces")
    assert resp.status_code == 503
    assert resp.json()["detail"]["reason"] == "duckdb_unavailable"


# ── /traces/{trace_id} ────────────────────────────────────────────────────────


def test_trace_detail_returns_span_tree(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        observability_service,
        "_spans_dir",
        lambda: tmp_path / "otel" / "spans",
    )
    trace = "0x" + "1" * 32
    _write_agent_run(tmp_path, trace_id=trace)
    client = TestClient(_make_app())

    resp = client.get(f"/api/observability/traces/{trace}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"] == trace
    assert len(body["spans"]) == 2
    # Spans are ordered by start_time ASC — root agent_run starts first.
    names = [s["name"] for s in body["spans"]]
    assert names == ["agent_run lead", "chat gpt-4o"]
    # Full attributes survive the round-trip
    root = next(s for s in body["spans"] if s["name"].startswith("agent_run"))
    assert root["attributes"]["gen_ai.agent.name"] == "lead"
    assert root["parent_span_id"] is None


def test_trace_detail_404_when_missing(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        observability_service,
        "_spans_dir",
        lambda: tmp_path / "otel" / "spans",
    )
    _write_agent_run(tmp_path, trace_id="0x" + "1" * 32)
    client = TestClient(_make_app())

    resp = client.get("/api/observability/traces/" + "0x" + "9" * 32)
    assert resp.status_code == 404
    assert resp.json()["detail"]["reason"] == "trace_not_found"


def test_trace_detail_503_when_duckdb_unavailable(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        observability_service,
        "_spans_dir",
        lambda: tmp_path / "otel" / "spans",
    )
    _write_agent_run(tmp_path)

    def _boom():
        raise DuckDBUnavailable("install the [otel] extra")

    monkeypatch.setattr(observability_service, "_try_import_duckdb", _boom)

    client = TestClient(_make_app())
    resp = client.get("/api/observability/traces/" + "0x" + "1" * 32)
    assert resp.status_code == 503
    assert resp.json()["detail"]["reason"] == "duckdb_unavailable"
