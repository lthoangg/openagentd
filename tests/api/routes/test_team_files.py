"""Tests for the team workspace-files listing endpoint.

Covers:
  GET /api/team/{session_id}/files    → recursive listing of agent workspace

Requirements validated:
  - session_id validated as UUID (400 on malformed)
  - Missing workspace dir returns an empty list (not 404) — fresh session
  - Nested files are surfaced with POSIX-separated relative paths
  - Dotfiles/dot-dirs are excluded
  - MIME types are guessed from the extension
  - Symlinks escaping the workspace root are skipped
  - Truncation flag flips when the file cap is exceeded
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("setup_db")


@pytest.fixture
def app_no_team():
    from app.api.app import create_app
    from app.services.team_manager import set_team

    app = create_app()
    set_team(None)
    yield app
    set_team(None)


@pytest.fixture
def client(app_no_team):
    return TestClient(app_no_team)


@pytest.fixture
def session_id() -> str:
    return str(uuid.uuid7())


class TestWorkspaceFilesListing:
    def test_invalid_session_id_returns_400(self, client):
        resp = client.get("/api/team/not-a-uuid/files")
        assert resp.status_code == 400

    def test_missing_workspace_returns_empty_list(
        self, client, session_id, tmp_path, monkeypatch
    ):
        """Fresh session: workspace dir doesn't exist yet — endpoint returns []
        rather than 404.  The UI needs a stable contract to render an empty
        state."""
        fake_root = tmp_path / "does-not-exist"

        from app.api.routes.team import files as team_routes

        monkeypatch.setattr(team_routes, "workspace_dir", lambda sid: fake_root)

        resp = client.get(f"/api/team/{session_id}/files")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session_id
        assert body["files"] == []
        assert body["truncated"] is False

    def test_lists_flat_files(self, client, session_id, tmp_path, monkeypatch):
        fake_root = tmp_path / "ws"
        fake_root.mkdir(parents=True)
        (fake_root / "notes.txt").write_text("hi")
        (fake_root / "readme.md").write_text("# hello")

        from app.api.routes.team import files as team_routes

        monkeypatch.setattr(team_routes, "workspace_dir", lambda sid: fake_root)

        resp = client.get(f"/api/team/{session_id}/files")
        assert resp.status_code == 200
        body = resp.json()
        paths = sorted(f["path"] for f in body["files"])
        assert paths == ["notes.txt", "readme.md"]
        # Each entry has the expected shape.
        for entry in body["files"]:
            assert entry["name"]
            assert entry["size"] >= 0
            assert isinstance(entry["mtime"], float)
            assert entry["mime"]

    def test_lists_nested_files_with_posix_paths(
        self, client, session_id, tmp_path, monkeypatch
    ):
        fake_root = tmp_path / "ws"
        (fake_root / "output").mkdir(parents=True)
        (fake_root / "output" / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (fake_root / "output" / "nested").mkdir()
        (fake_root / "output" / "nested" / "data.json").write_text("{}")

        from app.api.routes.team import files as team_routes

        monkeypatch.setattr(team_routes, "workspace_dir", lambda sid: fake_root)

        resp = client.get(f"/api/team/{session_id}/files")
        assert resp.status_code == 200
        paths = sorted(f["path"] for f in resp.json()["files"])
        # POSIX separators — safe to concat into ``/media/{path}``.
        assert paths == ["output/chart.png", "output/nested/data.json"]

    def test_mime_guessed_from_extension(
        self, client, session_id, tmp_path, monkeypatch
    ):
        fake_root = tmp_path / "ws"
        fake_root.mkdir()
        (fake_root / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (fake_root / "notes.txt").write_text("hi")
        (fake_root / "blob.bin").write_bytes(b"\x00\x01\x02")

        from app.api.routes.team import files as team_routes

        monkeypatch.setattr(team_routes, "workspace_dir", lambda sid: fake_root)

        resp = client.get(f"/api/team/{session_id}/files")
        by_name = {f["name"]: f for f in resp.json()["files"]}
        assert by_name["chart.png"]["mime"].startswith("image/")
        assert by_name["notes.txt"]["mime"].startswith("text/")
        # Unknown extension falls back to the octet-stream default.
        assert by_name["blob.bin"]["mime"] == "application/octet-stream"

    def test_dotfiles_and_dotdirs_excluded(
        self, client, session_id, tmp_path, monkeypatch
    ):
        """Hidden files (``.foo``) and files inside hidden dirs (``.git/…``)
        are skipped at every depth.  Users and agents shouldn't see noise
        like editor swap files or VCS internals."""
        fake_root = tmp_path / "ws"
        fake_root.mkdir()
        (fake_root / "visible.txt").write_text("ok")
        (fake_root / ".hidden").write_text("no")
        (fake_root / ".git").mkdir()
        (fake_root / ".git" / "HEAD").write_text("ref: …")
        (fake_root / "sub").mkdir()
        (fake_root / "sub" / ".swp").write_text("tmp")

        from app.api.routes.team import files as team_routes

        monkeypatch.setattr(team_routes, "workspace_dir", lambda sid: fake_root)

        resp = client.get(f"/api/team/{session_id}/files")
        paths = [f["path"] for f in resp.json()["files"]]
        assert paths == ["visible.txt"]

    def test_symlink_escaping_root_is_skipped(
        self, client, session_id, tmp_path, monkeypatch
    ):
        """A symlink inside the workspace that points outside must not leak
        the external file's metadata into the listing."""
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("top-secret")

        fake_root = tmp_path / "ws"
        fake_root.mkdir()
        (fake_root / "visible.txt").write_text("ok")
        # Create symlink inside workspace → outside.  On platforms that
        # don't allow symlinks (rare), skip cleanly.
        try:
            (fake_root / "escape.txt").symlink_to(secret)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation not supported on this platform")

        from app.api.routes.team import files as team_routes

        monkeypatch.setattr(team_routes, "workspace_dir", lambda sid: fake_root)

        resp = client.get(f"/api/team/{session_id}/files")
        paths = [f["path"] for f in resp.json()["files"]]
        assert "escape.txt" not in paths
        assert "visible.txt" in paths

    def test_truncation_when_over_cap(self, client, session_id, tmp_path, monkeypatch):
        """Beyond ``_MAX_FILES_LISTED`` the walk stops and ``truncated`` flips
        — a defensive ceiling so a pathological workspace can't blow up the
        response."""
        from app.api.routes.team import files as team_routes

        fake_root = tmp_path / "ws"
        fake_root.mkdir()
        # Generate one more file than the cap so truncation kicks in.
        cap = team_routes._MAX_FILES_LISTED
        for i in range(cap + 5):
            (fake_root / f"f{i:04d}.txt").write_text("x")

        monkeypatch.setattr(team_routes, "workspace_dir", lambda sid: fake_root)

        resp = client.get(f"/api/team/{session_id}/files")
        body = resp.json()
        assert body["truncated"] is True
        assert len(body["files"]) == cap
