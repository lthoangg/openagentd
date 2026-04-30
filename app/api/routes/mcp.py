"""MCP server CRUD: writes ``mcp.json`` and reconciles live runners."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agent.mcp import MCPServerStatus, mcp_manager
from app.agent.mcp.config import (
    HttpServerConfig,
    StdioServerConfig,
    load_config,
    save_config,
    validate_server_name,
)
from app.api.schemas.mcp import (
    CreateServerRequest,
    HttpServerBody,
    ServerDeleteResponse,
    ServerListResponse,
    ServerStatusResponse,
    StdioServerBody,
    UpdateServerRequest,
)

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────


def _config_to_body(
    cfg: StdioServerConfig | HttpServerConfig | None,
) -> StdioServerBody | HttpServerBody | None:
    if cfg is None:
        return None
    if isinstance(cfg, StdioServerConfig):
        return StdioServerBody(
            command=cfg.command,
            args=list(cfg.args),
            env=dict(cfg.env),
            enabled=cfg.enabled,
        )
    return HttpServerBody(
        url=cfg.url,
        headers=dict(cfg.headers),
        enabled=cfg.enabled,
    )


def _to_response(
    status: MCPServerStatus,
    config: StdioServerConfig | HttpServerConfig | None = None,
) -> ServerStatusResponse:
    return ServerStatusResponse(
        name=status.name,
        transport=status.transport,
        enabled=status.enabled,
        state=status.state,
        error=status.error,
        tool_names=list(status.tool_names),
        started_at=status.started_at,
        config=_config_to_body(config),
    )


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("/servers")
async def list_servers() -> ServerListResponse:
    cfg = load_config()
    return ServerListResponse(
        servers=[
            _to_response(s, cfg.servers.get(s.name)) for s in mcp_manager.list_status()
        ]
    )


@router.get("/servers/{name}")
async def get_server(name: str) -> ServerStatusResponse:
    status = mcp_manager.get_status(name)
    if status is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found.")
    cfg = load_config()
    return _to_response(status, cfg.servers.get(name))


@router.post("/servers", status_code=201)
async def create_server(body: CreateServerRequest) -> ServerStatusResponse:
    try:
        validate_server_name(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cfg = load_config()
    if body.name in cfg.servers:
        raise HTTPException(
            status_code=409, detail=f"MCP server '{body.name}' already exists."
        )

    server_cfg: StdioServerConfig | HttpServerConfig = body.server.to_config()
    cfg.servers[body.name] = server_cfg
    save_config(cfg)

    status = await mcp_manager.restart_server(body.name)
    return _to_response(status, server_cfg)


@router.put("/servers/{name}")
async def update_server(name: str, body: UpdateServerRequest) -> ServerStatusResponse:
    cfg = load_config()
    if name not in cfg.servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found.")

    server_cfg = body.server.to_config()
    cfg.servers[name] = server_cfg
    save_config(cfg)

    status = await mcp_manager.restart_server(name)
    return _to_response(status, server_cfg)


@router.delete("/servers/{name}")
async def delete_server(name: str) -> ServerDeleteResponse:
    cfg = load_config()
    if name not in cfg.servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found.")

    cfg.servers.pop(name)
    save_config(cfg)

    await mcp_manager.remove_runner(name)
    return ServerDeleteResponse(name=name)


@router.post("/servers/{name}/restart")
async def restart_server(name: str) -> ServerStatusResponse:
    try:
        status = await mcp_manager.restart_server(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"MCP server '{name}' not found."
        ) from exc
    cfg = load_config()
    return _to_response(status, cfg.servers.get(name))


@router.post("/apply")
async def apply_config() -> ServerListResponse:
    """Re-read ``mcp.json`` and reconcile every runner."""
    try:
        load_config()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await mcp_manager.reload_from_config()

    cfg = load_config()
    return ServerListResponse(
        servers=[
            _to_response(s, cfg.servers.get(s.name)) for s in mcp_manager.list_status()
        ]
    )
