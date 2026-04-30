"""Tests for app/agent/mcp/config.py — config schema and file I/O."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.mcp.config import (
    HttpServerConfig,
    MCPConfig,
    StdioServerConfig,
    load_config,
    save_config,
    validate_server_name,
)


class TestValidateServerName:
    """Test server name validation."""

    def test_valid_names(self) -> None:
        """Valid names match [a-zA-Z][a-zA-Z0-9_-]*."""
        assert validate_server_name("a") == "a"
        assert validate_server_name("A") == "A"
        assert validate_server_name("filesystem") == "filesystem"
        assert validate_server_name("my_server") == "my_server"
        assert validate_server_name("my-server") == "my-server"
        assert validate_server_name("MyServer123") == "MyServer123"

    def test_invalid_names(self) -> None:
        """Invalid names raise ValueError."""
        with pytest.raises(ValueError, match="Invalid MCP server name"):
            validate_server_name("1server")  # starts with digit
        with pytest.raises(ValueError, match="Invalid MCP server name"):
            validate_server_name("_server")  # starts with underscore
        with pytest.raises(ValueError, match="Invalid MCP server name"):
            validate_server_name("-server")  # starts with hyphen
        with pytest.raises(ValueError, match="Invalid MCP server name"):
            validate_server_name("bad name")  # contains space
        with pytest.raises(ValueError, match="Invalid MCP server name"):
            validate_server_name("bad.name")  # contains dot
        with pytest.raises(ValueError, match="Invalid MCP server name"):
            validate_server_name("")  # empty


class TestLoadConfig:
    """Test load_config function."""

    def test_load_config_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """load_config returns empty MCPConfig when file is missing."""
        config_file = tmp_path / "mcp.json"
        cfg = load_config(config_file)
        assert isinstance(cfg, MCPConfig)
        assert cfg.servers == {}

    def test_load_config_invalid_json_raises_error(self, tmp_path: Path) -> None:
        """load_config raises ValueError on invalid JSON."""
        config_file = tmp_path / "mcp.json"
        config_file.write_text("{ invalid json }")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_config(config_file)

    def test_load_config_not_dict_raises_error(self, tmp_path: Path) -> None:
        """load_config raises ValueError when top-level is not a dict."""
        config_file = tmp_path / "mcp.json"
        config_file.write_text('["array", "not", "dict"]')
        with pytest.raises(ValueError, match="expected a JSON object"):
            load_config(config_file)

    def test_load_config_schema_mismatch_raises_error(self, tmp_path: Path) -> None:
        """load_config raises ValueError on schema mismatch (extra=forbid)."""
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps({"unknown_field": "value"}))
        with pytest.raises(ValueError):
            load_config(config_file)

    def test_load_config_invalid_server_name_raises_error(self, tmp_path: Path) -> None:
        """load_config raises ValueError on invalid server name."""
        config_file = tmp_path / "mcp.json"
        config_file.write_text(
            json.dumps(
                {
                    "servers": {
                        "bad name": {
                            "transport": "stdio",
                            "command": "echo",
                        }
                    }
                }
            )
        )
        with pytest.raises(ValueError, match="Invalid MCP server name"):
            load_config(config_file)

    def test_load_config_stdio_roundtrip(self, tmp_path: Path) -> None:
        """save_config + load_config roundtrip for stdio config."""
        config_file = tmp_path / "mcp.json"
        original = MCPConfig(
            servers={
                "filesystem": StdioServerConfig(
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                    env={"FOO": "bar"},
                    enabled=True,
                )
            }
        )
        save_config(original, config_file)
        loaded = load_config(config_file)

        assert len(loaded.servers) == 1
        assert "filesystem" in loaded.servers
        server = loaded.servers["filesystem"]
        assert isinstance(server, StdioServerConfig)
        assert server.command == "npx"
        assert server.args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        assert server.env == {"FOO": "bar"}
        assert server.enabled is True

    def test_load_config_http_roundtrip(self, tmp_path: Path) -> None:
        """save_config + load_config roundtrip for http config."""
        config_file = tmp_path / "mcp.json"
        original = MCPConfig(
            servers={
                "github": HttpServerConfig(
                    url="https://mcp.example.com/v1",
                    headers={"Authorization": "Bearer token123"},
                    enabled=True,
                )
            }
        )
        save_config(original, config_file)
        loaded = load_config(config_file)

        assert len(loaded.servers) == 1
        assert "github" in loaded.servers
        server = loaded.servers["github"]
        assert isinstance(server, HttpServerConfig)
        assert server.url == "https://mcp.example.com/v1"
        assert server.headers == {"Authorization": "Bearer token123"}
        assert server.enabled is True

    def test_load_config_mixed_servers(self, tmp_path: Path) -> None:
        """load_config handles mixed stdio and http servers."""
        config_file = tmp_path / "mcp.json"
        original = MCPConfig(
            servers={
                "filesystem": StdioServerConfig(
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                ),
                "github": HttpServerConfig(
                    url="https://mcp.example.com/v1",
                ),
            }
        )
        save_config(original, config_file)
        loaded = load_config(config_file)

        assert len(loaded.servers) == 2
        assert isinstance(loaded.servers["filesystem"], StdioServerConfig)
        assert isinstance(loaded.servers["github"], HttpServerConfig)


class TestSaveConfig:
    """Test save_config function."""

    def test_save_config_creates_file(self, tmp_path: Path) -> None:
        """save_config creates the config file."""
        config_file = tmp_path / "mcp.json"
        cfg = MCPConfig(servers={"test": StdioServerConfig(command="echo")})
        result = save_config(cfg, config_file)
        assert result == config_file
        assert config_file.exists()

    def test_save_config_atomic_write(self, tmp_path: Path) -> None:
        """save_config writes atomically (no .tmp leftover)."""
        config_file = tmp_path / "mcp.json"
        cfg = MCPConfig(servers={"test": StdioServerConfig(command="echo")})
        save_config(cfg, config_file)

        # Check that the file exists and no .tmp files are left
        assert config_file.exists()
        tmp_files = list(tmp_path.glob(".mcp.json.*.tmp"))
        assert len(tmp_files) == 0

    def test_save_config_creates_parent_dirs(self, tmp_path: Path) -> None:
        """save_config creates parent directories if needed."""
        config_file = tmp_path / "subdir" / "nested" / "mcp.json"
        cfg = MCPConfig(servers={"test": StdioServerConfig(command="echo")})
        save_config(cfg, config_file)
        assert config_file.exists()

    def test_save_config_validates_server_names(self, tmp_path: Path) -> None:
        """save_config validates server names before writing."""
        config_file = tmp_path / "mcp.json"
        cfg = MCPConfig(servers={"bad name": StdioServerConfig(command="echo")})
        with pytest.raises(ValueError, match="Invalid MCP server name"):
            save_config(cfg, config_file)
        # File should not be created
        assert not config_file.exists()

    def test_save_config_json_format(self, tmp_path: Path) -> None:
        """save_config writes valid JSON with proper formatting."""
        config_file = tmp_path / "mcp.json"
        cfg = MCPConfig(
            servers={
                "test": StdioServerConfig(
                    command="echo",
                    args=["hello"],
                    env={"KEY": "value"},
                )
            }
        )
        save_config(cfg, config_file)

        # Verify it's valid JSON
        content = config_file.read_text()
        parsed = json.loads(content)
        assert "servers" in parsed
        assert "test" in parsed["servers"]

    def test_save_config_disabled_server(self, tmp_path: Path) -> None:
        """save_config preserves enabled=False flag."""
        config_file = tmp_path / "mcp.json"
        cfg = MCPConfig(
            servers={
                "disabled": StdioServerConfig(
                    command="echo",
                    enabled=False,
                )
            }
        )
        save_config(cfg, config_file)
        loaded = load_config(config_file)

        assert loaded.servers["disabled"].enabled is False
