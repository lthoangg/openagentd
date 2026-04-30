"""Tests for app/api/routes/settings.py — sandbox deny-list endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.sandbox_config import DEFAULT_DENIED_PATTERNS
from app.api.routes.settings import router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/settings")
    return app


@pytest.fixture
def isolated_config(tmp_path: Path):
    """Point load_config / save_config at a tmp ``sandbox.yaml``."""
    target = tmp_path / "sandbox.yaml"
    with patch("app.agent.sandbox_config.config_path", return_value=target):
        yield target


def test_get_sandbox_returns_seed_defaults_when_file_missing(
    isolated_config: Path,
) -> None:
    client = TestClient(_make_app())
    response = client.get("/api/settings/sandbox")
    assert response.status_code == 200
    assert response.json() == {"denied_patterns": list(DEFAULT_DENIED_PATTERNS)}
    # GET must not write the file.
    assert not isolated_config.exists()


def test_put_sandbox_persists_patterns(isolated_config: Path) -> None:
    client = TestClient(_make_app())
    body = {"denied_patterns": ["**/.env", "**/secrets/**"]}
    response = client.put("/api/settings/sandbox", json=body)
    assert response.status_code == 200
    assert response.json() == body
    assert isolated_config.exists()

    # Round-trip — GET reflects what was saved.
    again = client.get("/api/settings/sandbox")
    assert again.json() == body


def test_put_sandbox_strips_blank_patterns(isolated_config: Path) -> None:
    client = TestClient(_make_app())
    response = client.put(
        "/api/settings/sandbox",
        json={"denied_patterns": ["**/.env", "", "   ", "bar/*"]},
    )
    assert response.status_code == 200
    assert response.json() == {"denied_patterns": ["**/.env", "bar/*"]}


def test_put_sandbox_rejects_unknown_field(isolated_config: Path) -> None:
    client = TestClient(_make_app())
    response = client.put(
        "/api/settings/sandbox",
        json={"denied_patterns": [], "extra_field": "nope"},
    )
    assert response.status_code == 422
