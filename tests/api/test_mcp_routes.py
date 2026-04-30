"""Tests for app/api/routes/mcp.py — MCP server CRUD endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.mcp.config import MCPConfig, StdioServerConfig
from app.agent.mcp.manager import MCPServerStatus
from app.api.routes.mcp import router


def _make_app() -> FastAPI:
    """Create a test FastAPI app with the MCP router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/mcp")
    return app


class TestListServers:
    """Test GET /api/mcp/servers."""

    def test_list_servers_empty(self) -> None:
        """GET /api/mcp/servers returns 200 with empty list."""
        app = _make_app()
        with patch("app.api.routes.mcp.mcp_manager") as mock_manager:
            mock_manager.list_status.return_value = []
            client = TestClient(app)
            response = client.get("/api/mcp/servers")
            assert response.status_code == 200
            assert response.json() == {"servers": []}

    def test_list_servers_populated(self) -> None:
        """GET /api/mcp/servers returns list of servers."""
        app = _make_app()
        with patch("app.api.routes.mcp.mcp_manager") as mock_manager:
            status1 = MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=True,
                state="ready",
                tool_names=["mcp_filesystem_list"],
            )
            status2 = MCPServerStatus(
                name="github",
                transport="http",
                enabled=False,
                state="stopped",
            )
            mock_manager.list_status.return_value = [status1, status2]
            client = TestClient(app)
            response = client.get("/api/mcp/servers")
            assert response.status_code == 200
            data = response.json()
            assert len(data["servers"]) == 2
            assert data["servers"][0]["name"] == "filesystem"
            assert data["servers"][1]["name"] == "github"


class TestGetServer:
    """Test GET /api/mcp/servers/{name}."""

    def test_get_server_found(self) -> None:
        """GET /api/mcp/servers/{name} returns 200 with status."""
        app = _make_app()
        with patch("app.api.routes.mcp.mcp_manager") as mock_manager:
            status = MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=True,
                state="ready",
                tool_names=["mcp_filesystem_list"],
            )
            mock_manager.get_status.return_value = status
            client = TestClient(app)
            response = client.get("/api/mcp/servers/filesystem")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "filesystem"
            assert data["state"] == "ready"

    def test_get_server_not_found(self) -> None:
        """GET /api/mcp/servers/{name} returns 404 when missing."""
        app = _make_app()
        with patch("app.api.routes.mcp.mcp_manager") as mock_manager:
            mock_manager.get_status.return_value = None
            client = TestClient(app)
            response = client.get("/api/mcp/servers/missing")
            assert response.status_code == 404


class TestCreateServer:
    """Test POST /api/mcp/servers."""

    def test_create_server_stdio_success(self, tmp_path: Path) -> None:
        """POST /api/mcp/servers creates stdio server, returns 201."""
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager") as mock_manager,
            patch("app.api.routes.mcp.load_config") as mock_load,
            patch("app.api.routes.mcp.save_config") as mock_save,
        ):
            mock_load.return_value = MCPConfig()
            status = MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=True,
                state="ready",
            )
            mock_manager.restart_server = AsyncMock(return_value=status)

            client = TestClient(app)
            response = client.post(
                "/api/mcp/servers",
                json={
                    "name": "filesystem",
                    "server": {
                        "transport": "stdio",
                        "command": "npx",
                        "args": [
                            "-y",
                            "@modelcontextprotocol/server-filesystem",
                            "/tmp",
                        ],
                    },
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "filesystem"
            assert data["state"] == "ready"
            mock_save.assert_called_once()

    def test_create_server_http_success(self) -> None:
        """POST /api/mcp/servers creates http server, returns 201."""
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager") as mock_manager,
            patch("app.api.routes.mcp.load_config") as mock_load,
            patch("app.api.routes.mcp.save_config"),
        ):
            mock_load.return_value = MCPConfig()
            status = MCPServerStatus(
                name="github",
                transport="http",
                enabled=True,
                state="ready",
            )
            mock_manager.restart_server = AsyncMock(return_value=status)

            client = TestClient(app)
            response = client.post(
                "/api/mcp/servers",
                json={
                    "name": "github",
                    "server": {
                        "transport": "http",
                        "url": "https://mcp.example.com/v1",
                        "headers": {"Authorization": "Bearer token"},
                    },
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "github"

    def test_create_server_duplicate_name_returns_409(self) -> None:
        """POST /api/mcp/servers with duplicate name returns 409."""
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager"),
            patch("app.api.routes.mcp.load_config") as mock_load,
            patch("app.api.routes.mcp.save_config"),
        ):
            existing_cfg = MCPConfig(
                servers={"filesystem": StdioServerConfig(command="echo")}
            )
            mock_load.return_value = existing_cfg

            client = TestClient(app)
            response = client.post(
                "/api/mcp/servers",
                json={
                    "name": "filesystem",
                    "server": {
                        "transport": "stdio",
                        "command": "npx",
                    },
                },
            )
            assert response.status_code == 409

    def test_create_server_invalid_name_returns_422(self) -> None:
        """POST /api/mcp/servers with invalid name returns 422."""
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager"),
            patch("app.api.routes.mcp.load_config") as mock_load,
            patch("app.api.routes.mcp.save_config"),
        ):
            mock_load.return_value = MCPConfig()

            client = TestClient(app)
            response = client.post(
                "/api/mcp/servers",
                json={
                    "name": "bad name",  # Invalid: contains space
                    "server": {
                        "transport": "stdio",
                        "command": "echo",
                    },
                },
            )
            assert response.status_code == 422

    def test_create_server_does_not_reload_team(self) -> None:
        """POST /api/mcp/servers must NOT trigger team_manager.reload().

        Mid-turn reloads tear down in-flight tool execution and rotate
        session IDs.  Agents instead pick up new MCP tools at the start
        of their next turn via the config-stamp drift check.
        """
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager") as mock_manager,
            patch("app.api.routes.mcp.load_config") as mock_load,
            patch("app.api.routes.mcp.save_config"),
            # If the route accidentally re-introduces a team_manager
            # import, this patch will succeed AND the AsyncMock below
            # will record any reload() calls.  Sentinel-style assertion.
            patch("app.services.team_manager.reload") as mock_reload,
        ):
            mock_load.return_value = MCPConfig()
            status = MCPServerStatus(
                name="test",
                transport="stdio",
                enabled=True,
                state="ready",
            )
            mock_manager.restart_server = AsyncMock(return_value=status)
            mock_reload.return_value = AsyncMock()

            client = TestClient(app)
            response = client.post(
                "/api/mcp/servers",
                json={
                    "name": "test",
                    "server": {
                        "transport": "stdio",
                        "command": "echo",
                    },
                },
            )
            assert response.status_code == 201
            mock_reload.assert_not_called()


class TestUpdateServer:
    """Test PUT /api/mcp/servers/{name}."""

    def test_update_server_success(self) -> None:
        """PUT /api/mcp/servers/{name} updates existing server."""
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager") as mock_manager,
            patch("app.api.routes.mcp.load_config") as mock_load,
            patch("app.api.routes.mcp.save_config") as mock_save,
        ):
            existing_cfg = MCPConfig(
                servers={"test": StdioServerConfig(command="echo")}
            )
            mock_load.return_value = existing_cfg
            status = MCPServerStatus(
                name="test",
                transport="stdio",
                enabled=True,
                state="ready",
            )
            mock_manager.restart_server = AsyncMock(return_value=status)

            client = TestClient(app)
            response = client.put(
                "/api/mcp/servers/test",
                json={
                    "server": {
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["new-arg"],
                    },
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test"
            mock_save.assert_called_once()

    def test_update_server_not_found_returns_404(self) -> None:
        """PUT /api/mcp/servers/{name} returns 404 when missing."""
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager"),
            patch("app.api.routes.mcp.load_config") as mock_load,
            patch("app.api.routes.mcp.save_config"),
        ):
            mock_load.return_value = MCPConfig()

            client = TestClient(app)
            response = client.put(
                "/api/mcp/servers/missing",
                json={
                    "server": {
                        "transport": "stdio",
                        "command": "echo",
                    },
                },
            )
            assert response.status_code == 404


class TestDeleteServer:
    """Test DELETE /api/mcp/servers/{name}."""

    def test_delete_server_success(self) -> None:
        """DELETE /api/mcp/servers/{name} removes server entry."""
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager") as mock_manager,
            patch("app.api.routes.mcp.load_config") as mock_load,
            patch("app.api.routes.mcp.save_config") as mock_save,
        ):
            existing_cfg = MCPConfig(
                servers={"test": StdioServerConfig(command="echo")}
            )
            mock_load.return_value = existing_cfg
            mock_manager.remove_runner = AsyncMock()

            client = TestClient(app)
            response = client.delete("/api/mcp/servers/test")
            assert response.status_code == 200
            data = response.json()
            assert data == {"name": "test"}
            mock_save.assert_called_once()
            mock_manager.remove_runner.assert_called_once_with("test")

    def test_delete_server_not_found_returns_404(self) -> None:
        """DELETE /api/mcp/servers/{name} returns 404 when missing."""
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager"),
            patch("app.api.routes.mcp.load_config") as mock_load,
            patch("app.api.routes.mcp.save_config"),
        ):
            mock_load.return_value = MCPConfig()

            client = TestClient(app)
            response = client.delete("/api/mcp/servers/missing")
            assert response.status_code == 404


class TestRestartServer:
    """Test POST /api/mcp/servers/{name}/restart."""

    def test_restart_server_success(self) -> None:
        """POST /api/mcp/servers/{name}/restart restarts server."""
        app = _make_app()
        with patch("app.api.routes.mcp.mcp_manager") as mock_manager:
            status = MCPServerStatus(
                name="test",
                transport="stdio",
                enabled=True,
                state="ready",
            )
            mock_manager.restart_server = AsyncMock(return_value=status)

            client = TestClient(app)
            response = client.post("/api/mcp/servers/test/restart")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test"
            mock_manager.restart_server.assert_called_once_with("test")

    def test_restart_server_not_found_returns_404(self) -> None:
        """POST /api/mcp/servers/{name}/restart returns 404 when missing."""
        app = _make_app()
        with patch("app.api.routes.mcp.mcp_manager") as mock_manager:
            mock_manager.restart_server = AsyncMock(side_effect=KeyError("test"))

            client = TestClient(app)
            response = client.post("/api/mcp/servers/missing/restart")
            assert response.status_code == 404


class TestApply:
    """POST /api/mcp/apply — re-read mcp.json and reconcile every runner.

    The endpoint is the hook the mcp-installer skill's ``apply`` script
    calls after editing the config file directly. It must:
      1. Validate the file BEFORE tearing anything down (422 on bad file).
      2. Call ``mcp_manager.reload_from_config()`` to reconcile runners.
      3. Return the new server list with saved config payloads attached.

    Crucially it must NOT reload the team — agents pick up new MCP
    tools at the start of their next turn via the config-stamp drift
    check, so reloads don't tear down in-flight tool execution.
    """

    def test_apply_success_returns_server_list(self) -> None:
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager") as mock_manager,
            patch("app.api.routes.mcp.load_config") as mock_load,
            patch("app.services.team_manager.reload") as mock_reload,
        ):
            cfg = MCPConfig(
                servers={"fs": StdioServerConfig(command="npx", args=["-y", "x"])}
            )
            mock_load.return_value = cfg
            mock_manager.reload_from_config = AsyncMock()
            mock_manager.list_status.return_value = [
                MCPServerStatus(
                    name="fs",
                    transport="stdio",
                    enabled=True,
                    state="ready",
                    tool_names=["mcp_fs_read"],
                )
            ]

            client = TestClient(app)
            response = client.post("/api/mcp/apply")

            assert response.status_code == 200
            data = response.json()
            assert [s["name"] for s in data["servers"]] == ["fs"]
            assert data["servers"][0]["state"] == "ready"
            # Saved config is projected into the response so the caller
            # doesn't need a follow-up GET to see what was applied.
            assert data["servers"][0]["config"]["transport"] == "stdio"
            assert data["servers"][0]["config"]["command"] == "npx"
            mock_manager.reload_from_config.assert_awaited_once()
            # Team must NOT be reloaded — drift detection picks up
            # tool changes on the next turn instead.
            mock_reload.assert_not_called()

    def test_apply_rejects_malformed_config_with_422(self) -> None:
        """A bad mcp.json must NOT trigger reload_from_config."""
        app = _make_app()
        with (
            patch("app.api.routes.mcp.mcp_manager") as mock_manager,
            patch("app.api.routes.mcp.load_config") as mock_load,
        ):
            mock_load.side_effect = ValueError("Invalid JSON in mcp.json")
            mock_manager.reload_from_config = AsyncMock()

            client = TestClient(app)
            response = client.post("/api/mcp/apply")

            assert response.status_code == 422
            assert "Invalid JSON" in response.json()["detail"]
            # Crucially: we must not have torn down healthy runners.
            mock_manager.reload_from_config.assert_not_awaited()
