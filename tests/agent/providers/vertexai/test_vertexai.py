"""Tests for app/providers/vertexai/vertexai.py."""

from __future__ import annotations

import pytest

from app.agent.providers.vertexai import VertexAIProvider


class TestVertexAIProviderInit:
    def test_express_mode_defaults(self):
        """No project → express mode URL."""
        prov = VertexAIProvider(api_key="test-key", model="gemini-2.0-flash")
        assert prov.model == "gemini-2.0-flash"
        assert prov.api_key == "test-key"
        assert prov.project is None
        assert "aiplatform.googleapis.com" in prov.base_url
        assert prov.location == "global"

    def test_normal_mode_with_location(self):
        """project + non-global location → regional endpoint."""
        prov = VertexAIProvider(
            api_key="key",
            model="gemini-pro",
            project="my-project",
            location="us-central1",
        )
        assert "us-central1-aiplatform" in prov.base_url
        assert prov.project == "my-project"

    def test_normal_mode_global_location(self):
        """project + global location → non-regional endpoint."""
        prov = VertexAIProvider(
            api_key="key",
            model="gemini-pro",
            project="my-project",
            location="global",
        )
        assert "us-central1" not in prov.base_url
        assert "aiplatform.googleapis.com" in prov.base_url

    def test_missing_api_key_raises(self):
        with pytest.raises(ValueError, match="API key is required"):
            VertexAIProvider(api_key="", model="gemini-pro")

    def test_secret_str_api_key(self):
        from pydantic import SecretStr

        prov = VertexAIProvider(api_key=SecretStr("secret-key"), model="gemini-pro")
        assert prov.api_key == "secret-key"


class TestVertexAIProviderMethods:
    def test_auth_headers(self):
        prov = VertexAIProvider(api_key="my-key", model="gemini-pro")
        headers = prov._auth_headers()
        assert headers == {"x-goog-api-key": "my-key"}

    def test_build_url_express(self):
        prov = VertexAIProvider(api_key="key", model="gemini-2.0-flash")
        url = prov._build_url("streamGenerateContent")
        assert "publishers/google/models/gemini-2.0-flash" in url
        assert "streamGenerateContent" in url
        assert "projects" not in url

    def test_build_url_normal(self):
        prov = VertexAIProvider(
            api_key="key",
            model="gemini-pro",
            project="proj-1",
            location="europe-west1",
        )
        url = prov._build_url("generateContent")
        assert "projects/proj-1" in url
        assert "locations/europe-west1" in url
        assert "publishers/google/models/gemini-pro" in url
        assert "generateContent" in url
