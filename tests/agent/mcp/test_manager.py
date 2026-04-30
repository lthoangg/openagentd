"""Tests for app/agent/mcp/manager.py — MCPManager lifecycle."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.agent.mcp.config import MCPConfig, StdioServerConfig
from app.agent.mcp.manager import MCPManager, MCPServerStatus
from app.agent.mcp.tools import MCPTool


class TestMCPManagerStartStop:
    """Test MCPManager lifecycle."""

    @pytest.mark.asyncio
    async def test_start_no_config_file_logs_and_returns(self, tmp_path: Path) -> None:
        """MCPManager.start() with no config file just logs and returns."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            mock_load.return_value = MCPConfig()
            await manager.start()
            assert manager._runners == {}
            assert manager._started is True

    @pytest.mark.asyncio
    async def test_start_invalid_config_logs_error(self, tmp_path: Path) -> None:
        """MCPManager.start() logs error on invalid config and returns."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            mock_load.side_effect = ValueError("Invalid config")
            await manager.start()
            assert manager._runners == {}
            assert manager._started is True

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self) -> None:
        """MCPManager.start() / stop() lifecycle when no servers configured."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            mock_load.return_value = MCPConfig()
            await manager.start()
            assert manager._started is True

            await manager.stop()
            assert manager._started is False
            assert manager._runners == {}

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        """MCPManager.start() is idempotent — calling twice is safe."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            mock_load.return_value = MCPConfig()
            await manager.start()
            await manager.start()  # Second call should be no-op
            assert manager._started is True
            assert mock_load.call_count == 1  # Only called once

    @pytest.mark.asyncio
    async def test_stop_when_not_started_is_noop(self) -> None:
        """MCPManager.stop() is safe when not started."""
        manager = MCPManager()
        await manager.stop()  # Should not raise
        assert manager._started is False


class TestMCPManagerListStatus:
    """Test MCPManager.list_status()."""

    @pytest.mark.asyncio
    async def test_list_status_empty(self) -> None:
        """list_status() returns empty list when no servers."""
        manager = MCPManager()
        status_list = manager.list_status()
        assert status_list == []

    @pytest.mark.asyncio
    async def test_list_status_disabled_servers(self) -> None:
        """list_status() returns disabled servers correctly with state=stopped."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            cfg = MCPConfig(
                servers={
                    "disabled": StdioServerConfig(
                        command="echo",
                        enabled=False,
                    )
                }
            )
            mock_load.return_value = cfg
            await manager.start()

            status_list = manager.list_status()
            assert len(status_list) == 1
            assert status_list[0].name == "disabled"
            assert status_list[0].state == "stopped"
            assert status_list[0].enabled is False

    @pytest.mark.asyncio
    async def test_list_status_multiple_servers(self) -> None:
        """list_status() returns all configured servers."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            cfg = MCPConfig(
                servers={
                    "server1": StdioServerConfig(command="echo", enabled=False),
                    "server2": StdioServerConfig(command="echo", enabled=False),
                }
            )
            mock_load.return_value = cfg
            await manager.start()

            status_list = manager.list_status()
            assert len(status_list) == 2
            names = {s.name for s in status_list}
            assert names == {"server1", "server2"}


class TestMCPManagerGetStatus:
    """Test MCPManager.get_status()."""

    @pytest.mark.asyncio
    async def test_get_status_missing_returns_none(self) -> None:
        """get_status() returns None for missing server."""
        manager = MCPManager()
        status = manager.get_status("nonexistent")
        assert status is None

    @pytest.mark.asyncio
    async def test_get_status_existing_server(self) -> None:
        """get_status() returns status for existing server."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            cfg = MCPConfig(
                servers={"test": StdioServerConfig(command="echo", enabled=False)}
            )
            mock_load.return_value = cfg
            await manager.start()

            status = manager.get_status("test")
            assert status is not None
            assert status.name == "test"
            assert status.state == "stopped"


class TestMCPManagerGetToolsDict:
    """Test MCPManager.get_tools_dict()."""

    @pytest.mark.asyncio
    async def test_get_tools_dict_empty(self) -> None:
        """get_tools_dict() returns empty when no servers ready."""
        manager = MCPManager()
        tools = manager.get_tools_dict()
        assert tools == {}

    @pytest.mark.asyncio
    async def test_get_tools_dict_disabled_servers_excluded(self) -> None:
        """get_tools_dict() excludes disabled servers."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            cfg = MCPConfig(
                servers={"disabled": StdioServerConfig(command="echo", enabled=False)}
            )
            mock_load.return_value = cfg
            await manager.start()

            tools = manager.get_tools_dict()
            assert tools == {}

    @pytest.mark.asyncio
    async def test_get_tools_dict_only_ready_servers(self) -> None:
        """get_tools_dict() only includes tools from ready servers."""
        manager = MCPManager()

        # Create mock runners with different states
        ready_runner = MagicMock()
        ready_runner.status.state = "ready"
        ready_tool = MagicMock()
        ready_tool.name = "mcp_ready_tool1"
        ready_runner.tools = [ready_tool]

        error_runner = MagicMock()
        error_runner.status.state = "error"
        error_runner.tools = []

        manager._runners = {
            "ready_server": ready_runner,
            "error_server": error_runner,
        }

        tools = manager.get_tools_dict()
        assert len(tools) == 1
        assert "mcp_ready_tool1" in tools


class TestMCPManagerRemoveRunner:
    """Test MCPManager.remove_runner()."""

    @pytest.mark.asyncio
    async def test_remove_runner_noop_when_absent(self) -> None:
        """remove_runner() is a no-op when name not present."""
        manager = MCPManager()
        await manager.remove_runner("nonexistent")  # Should not raise
        assert manager._runners == {}

    @pytest.mark.asyncio
    async def test_remove_runner_removes_existing(self) -> None:
        """remove_runner() removes an existing runner."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            cfg = MCPConfig(
                servers={"test": StdioServerConfig(command="echo", enabled=False)}
            )
            mock_load.return_value = cfg
            await manager.start()

            assert "test" in manager._runners
            await manager.remove_runner("test")
            assert "test" not in manager._runners


class TestMCPManagerWithMockedServer:
    """Test MCPManager with mocked _run_server."""

    @pytest.mark.asyncio
    async def test_spawn_runner_with_mocked_server(self) -> None:
        """MCPManager spawns runners and sets status correctly."""
        manager = MCPManager()

        async def mock_run_server(name, server_cfg, runner):
            """Mock _run_server that sets up a ready runner."""
            runner.session = MagicMock()
            mcp_tool = SimpleNamespace(
                name="list_files",
                description="A test tool",
                inputSchema={"type": "object"},
            )
            runner.tools = [
                MCPTool(
                    server_name=name,
                    mcp_tool=mcp_tool,  # type: ignore[arg-type]
                    session_provider=lambda r=runner: r.session,
                )
            ]
            runner.status = MCPServerStatus(
                name=name,
                transport=server_cfg.transport,
                enabled=True,
                state="ready",
                tool_names=["mcp_test_list_files"],
            )
            runner.ready.set()
            await runner.shutdown.wait()

        with patch("app.agent.mcp.manager.load_config") as mock_load:
            cfg = MCPConfig(
                servers={"test": StdioServerConfig(command="echo", enabled=True)}
            )
            mock_load.return_value = cfg

            with patch.object(manager, "_run_server", side_effect=mock_run_server):
                await manager.start()

                # Wait for ready
                runner = manager._runners["test"]
                await asyncio.wait_for(runner.ready.wait(), timeout=1.0)

                # Check status
                status = manager.get_status("test")
                assert status is not None
                assert status.state == "ready"
                assert status.tool_names == ["mcp_test_list_files"]

                # Check tools
                tools = manager.get_tools_dict()
                assert "mcp_test_list_files" in tools

                # Cleanup
                await manager.stop()

    @pytest.mark.asyncio
    async def test_restart_server_with_mocked_server(self) -> None:
        """MCPManager.restart_server() restarts a server."""
        manager = MCPManager()

        async def mock_run_server(name, server_cfg, runner):
            """Mock _run_server."""
            runner.session = MagicMock()
            runner.tools = []
            runner.status = MCPServerStatus(
                name=name,
                transport=server_cfg.transport,
                enabled=True,
                state="ready",
            )
            runner.ready.set()
            await runner.shutdown.wait()

        with patch("app.agent.mcp.manager.load_config") as mock_load:
            cfg = MCPConfig(
                servers={"test": StdioServerConfig(command="echo", enabled=True)}
            )
            mock_load.return_value = cfg

            with patch.object(manager, "_run_server", side_effect=mock_run_server):
                await manager.start()
                runner = manager._runners["test"]
                await asyncio.wait_for(runner.ready.wait(), timeout=1.0)

                # Restart
                status = await manager.restart_server("test")
                assert status.name == "test"

                # Cleanup
                await manager.stop()

    @pytest.mark.asyncio
    async def test_restart_server_missing_raises_keyerror(self) -> None:
        """MCPManager.restart_server() raises KeyError for missing server."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            mock_load.return_value = MCPConfig()
            with pytest.raises(KeyError):
                await manager.restart_server("nonexistent")

    @pytest.mark.asyncio
    async def test_reload_from_config(self) -> None:
        """MCPManager.reload_from_config() restarts all servers."""
        manager = MCPManager()

        async def mock_run_server(name, server_cfg, runner):
            """Mock _run_server."""
            runner.session = MagicMock()
            runner.tools = []
            runner.status = MCPServerStatus(
                name=name,
                transport=server_cfg.transport,
                enabled=True,
                state="ready",
            )
            runner.ready.set()
            await runner.shutdown.wait()

        with patch("app.agent.mcp.manager.load_config") as mock_load:
            cfg = MCPConfig(
                servers={"test": StdioServerConfig(command="echo", enabled=True)}
            )
            mock_load.return_value = cfg

            with patch.object(manager, "_run_server", side_effect=mock_run_server):
                await manager.start()
                assert len(manager._runners) == 1

                # Reload
                await manager.reload_from_config()
                assert len(manager._runners) == 1

                # Cleanup
                await manager.stop()

    @pytest.mark.asyncio
    async def test_start_sets_started_flag_even_on_invalid_config(self) -> None:
        """MCPManager.start() sets _started=True even when config is invalid."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            mock_load.side_effect = ValueError("Bad config")
            await manager.start()
            # _started must be True so subsequent calls don't retry
            assert manager._started is True

    @pytest.mark.asyncio
    async def test_disabled_server_has_no_task(self) -> None:
        """Disabled servers have task=None, not a dummy task."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            cfg = MCPConfig(
                servers={"disabled": StdioServerConfig(command="echo", enabled=False)}
            )
            mock_load.return_value = cfg
            await manager.start()

            runner = manager._runners["disabled"]
            assert runner.task is None

    @pytest.mark.asyncio
    async def test_stop_runner_with_disabled_server_noop(self) -> None:
        """_stop_runner is safe when runner.task is None."""
        manager = MCPManager()
        with patch("app.agent.mcp.manager.load_config") as mock_load:
            cfg = MCPConfig(
                servers={"disabled": StdioServerConfig(command="echo", enabled=False)}
            )
            mock_load.return_value = cfg
            await manager.start()

            # Should not raise even though task is None
            await manager._stop_runner("disabled")
            assert "disabled" in manager._runners

    @pytest.mark.asyncio
    async def test_restart_server_disabled_to_enabled(self) -> None:
        """restart_server can transition a disabled server to enabled."""
        manager = MCPManager()

        async def mock_run_server(name, server_cfg, runner):
            runner.session = MagicMock()
            runner.tools = []
            runner.status = MCPServerStatus(
                name=name,
                transport=server_cfg.transport,
                enabled=True,
                state="ready",
            )
            runner.ready.set()
            await runner.shutdown.wait()

        with patch("app.agent.mcp.manager.load_config") as mock_load:
            # Start with disabled server
            cfg = MCPConfig(
                servers={"test": StdioServerConfig(command="echo", enabled=False)}
            )
            mock_load.return_value = cfg
            await manager.start()

            runner = manager._runners["test"]
            assert runner.task is None

            # Now enable it
            cfg.servers["test"].enabled = True
            with patch.object(manager, "_run_server", side_effect=mock_run_server):
                status = await manager.restart_server("test")
                assert status.enabled is True
                assert status.state == "ready"
                # Now it should have a task
                assert manager._runners["test"].task is not None

            await manager.stop()

    @pytest.mark.asyncio
    async def test_reload_from_config_with_invalid_config(self) -> None:
        """reload_from_config handles invalid config gracefully."""
        manager = MCPManager()

        async def mock_run_server(name, server_cfg, runner):
            runner.session = MagicMock()
            runner.tools = []
            runner.status = MCPServerStatus(
                name=name,
                transport=server_cfg.transport,
                enabled=True,
                state="ready",
            )
            runner.ready.set()
            await runner.shutdown.wait()

        with patch("app.agent.mcp.manager.load_config") as mock_load:
            # Start with valid config
            cfg = MCPConfig(
                servers={"test": StdioServerConfig(command="echo", enabled=True)}
            )
            mock_load.return_value = cfg

            with patch.object(manager, "_run_server", side_effect=mock_run_server):
                await manager.start()
                assert len(manager._runners) == 1

                # Now make config invalid
                mock_load.side_effect = ValueError("Bad config")
                await manager.reload_from_config()

                # Runners should be cleared and _started should be True
                assert len(manager._runners) == 0
                assert manager._started is True


class TestWaitUntilReady:
    """Test MCPManager.wait_until_ready()."""

    @pytest.mark.asyncio
    async def test_no_runners_returns_immediately(self) -> None:
        manager = MCPManager()
        # No timeout needed; should be effectively instant.
        await asyncio.wait_for(manager.wait_until_ready(timeout=5.0), timeout=1.0)

    @pytest.mark.asyncio
    async def test_returns_when_all_runners_ready(self) -> None:
        """Returns as soon as every runner's `ready` event fires."""
        from app.agent.mcp.manager import _ServerRunner

        manager = MCPManager()
        for name in ("a", "b"):
            r = _ServerRunner(
                shutdown=asyncio.Event(),
                ready=asyncio.Event(),
                status=MCPServerStatus(
                    name=name, transport="stdio", enabled=True, state="starting"
                ),
            )
            manager._runners[name] = r

        async def flip_after_delay() -> None:
            await asyncio.sleep(0.01)
            for r in manager._runners.values():
                r.ready.set()

        flipper = asyncio.create_task(flip_after_delay())
        await manager.wait_until_ready(timeout=1.0)
        await flipper

    @pytest.mark.asyncio
    async def test_timeout_logs_warning_does_not_raise(self, caplog) -> None:
        """A runner that never becomes ready triggers a warning, no exception."""
        from app.agent.mcp.manager import _ServerRunner

        manager = MCPManager()
        manager._runners["stuck"] = _ServerRunner(
            shutdown=asyncio.Event(),
            ready=asyncio.Event(),  # never set
            status=MCPServerStatus(
                name="stuck", transport="stdio", enabled=True, state="starting"
            ),
        )
        # Short timeout so the test stays fast.
        await manager.wait_until_ready(timeout=0.05)
        # Runner is left in `starting` state — caller (lifespan) proceeds.
        assert manager._runners["stuck"].status.state == "starting"
