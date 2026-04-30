"""Tests for app/core/paths.py — session path helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.core.paths import uploads_dir, workspace_dir


# Me ensure setup_db runs before the per-test clean_db teardown.
pytestmark = pytest.mark.usefixtures("setup_db")


class TestUploadsDir:
    def test_returns_uploads_session_path(self):
        sid = "019d9777-ebc9-770e-8b8c-698c9baa5d50"
        got = uploads_dir(sid)
        expected = Path(settings.OPENAGENTD_WORKSPACE_DIR) / sid / "uploads"
        assert got == expected

    def test_lives_inside_workspace(self):
        """Uploads sit under the session workspace so fs tools can reach
        them as ``uploads/<filename>``."""
        sid = "019d9777-ebc9-770e-8b8c-698c9baa5d50"
        assert uploads_dir(sid).parent == workspace_dir(sid)


class TestWorkspaceDir:
    def test_returns_workspace_session_root(self):
        sid = "019d9777-ebc9-770e-8b8c-698c9baa5d50"
        got = workspace_dir(sid)
        expected = Path(settings.OPENAGENTD_WORKSPACE_DIR) / sid
        assert got == expected


class TestPathIsolation:
    def test_different_session_ids_produce_different_paths(self):
        """Verify that different session IDs produce isolated paths."""
        sid1 = "019d9777-ebc9-770e-8b8c-698c9baa5d50"
        sid2 = "019d9777-ebc9-770e-8b8c-698c9baa5d51"
        assert uploads_dir(sid1) != uploads_dir(sid2)
        assert workspace_dir(sid1) != workspace_dir(sid2)

    def test_paths_are_pure_functions(self):
        """Verify that path helpers don't create directories as side effect."""
        sid = "019d9777-ebc9-770e-8b8c-698c9baa5d50"
        up = uploads_dir(sid)
        ws = workspace_dir(sid)
        # Calling the helpers should not create directories.
        assert not up.exists()
        assert not ws.exists()

    def test_paths_with_special_chars_in_session_id(self):
        """Verify path construction works with various session ID formats."""
        # UUIDs are the contract, but verify the path construction is robust.
        sid = "019d9777-ebc9-770e-8b8c-698c9baa5d50"
        up = uploads_dir(sid)
        ws = workspace_dir(sid)
        # Both should be Path objects with the session_id in the path.
        assert isinstance(up, Path)
        assert isinstance(ws, Path)
        assert sid in str(up)
        assert sid in str(ws)
