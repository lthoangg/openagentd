"""Tests for app/core/middlewares.py — RequestSizeLimitMiddleware + SecurityHeadersMiddleware."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middlewares import RequestSizeLimitMiddleware, SecurityHeadersMiddleware


def _make_app(max_bytes: int = 100) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=max_bytes)

    @app.post("/upload")
    async def upload():
        return {"ok": True}

    return app


class TestRequestSizeLimitMiddleware:
    def test_request_within_limit_passes_through(self):
        client = TestClient(_make_app(max_bytes=100))
        resp = client.post(
            "/upload",
            content=b"x" * 50,
            headers={"Content-Length": "50"},
        )
        assert resp.status_code == 200

    def test_request_exactly_at_limit_passes_through(self):
        client = TestClient(_make_app(max_bytes=100))
        resp = client.post(
            "/upload",
            content=b"x" * 100,
            headers={"Content-Length": "100"},
        )
        assert resp.status_code == 200

    def test_request_exceeding_limit_returns_413(self):
        client = TestClient(_make_app(max_bytes=100))
        resp = client.post(
            "/upload",
            content=b"x" * 101,
            headers={"Content-Length": "101"},
        )
        assert resp.status_code == 413

    def test_413_body_contains_detail(self):
        client = TestClient(_make_app(max_bytes=10))
        resp = client.post(
            "/upload",
            content=b"x" * 20,
            headers={"Content-Length": "20"},
        )
        assert resp.json() == {"detail": "Request body too large."}

    def test_no_content_length_header_passes_through(self):
        """Requests without Content-Length (chunked) are allowed."""
        app = FastAPI()
        app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10)

        @app.post("/upload")
        async def upload():
            return {"ok": True}

        client = TestClient(app)
        # Send without explicit Content-Length by using params-based body
        resp = client.post("/upload")
        assert resp.status_code == 200

    def test_default_max_bytes_is_4mb(self):
        middleware = RequestSizeLimitMiddleware(app=FastAPI())
        assert middleware._max_bytes == 4 * 1024 * 1024

    def test_custom_max_bytes_stored(self):
        middleware = RequestSizeLimitMiddleware(app=FastAPI(), max_bytes=1024)
        assert middleware._max_bytes == 1024


# ── SecurityHeadersMiddleware ────────────────────────────────────────────────


def _make_secure_app(**kwargs) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, **kwargs)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/custom-csp")
    async def custom():
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"ok": True},
            headers={"Content-Security-Policy": "default-src 'none'"},
        )

    return app


class TestSecurityHeadersMiddleware:
    def test_default_headers_present(self):
        client = TestClient(_make_secure_app())
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "no-referrer"
        assert "geolocation=()" in resp.headers["Permissions-Policy"]
        assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"
        assert resp.headers["Cross-Origin-Resource-Policy"] == "same-origin"
        assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]

    def test_hsts_disabled_by_default(self):
        client = TestClient(_make_secure_app())
        resp = client.get("/ping")
        assert "Strict-Transport-Security" not in resp.headers

    def test_hsts_enabled_on_request(self):
        client = TestClient(_make_secure_app(enable_hsts=True))
        resp = client.get("/ping")
        assert resp.headers["Strict-Transport-Security"].startswith("max-age=")
        assert "includeSubDomains" in resp.headers["Strict-Transport-Security"]

    def test_extra_headers_override_defaults(self):
        client = TestClient(
            _make_secure_app(extra_headers={"Referrer-Policy": "same-origin"})
        )
        resp = client.get("/ping")
        assert resp.headers["Referrer-Policy"] == "same-origin"

    def test_extra_headers_empty_string_removes_default(self):
        client = TestClient(_make_secure_app(extra_headers={"X-Frame-Options": ""}))
        resp = client.get("/ping")
        assert "X-Frame-Options" not in resp.headers
        # Other defaults still there.
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_route_set_header_is_not_overwritten(self):
        """If the route already sets CSP, middleware must not clobber it."""
        client = TestClient(_make_secure_app())
        resp = client.get("/custom-csp")
        assert resp.headers["Content-Security-Policy"] == "default-src 'none'"
        # But other defaults still attached.
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
