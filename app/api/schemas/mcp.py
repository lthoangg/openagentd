"""Request and response schemas for ``/api/mcp`` endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.mcp.config import HttpServerConfig, StdioServerConfig


class StdioServerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["stdio"] = "stdio"
    command: Annotated[str, Field(min_length=1)]
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    def to_config(self) -> StdioServerConfig:
        return StdioServerConfig(
            command=self.command,
            args=self.args,
            env=self.env,
            enabled=self.enabled,
        )


class HttpServerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["http"] = "http"
    url: Annotated[str, Field(min_length=1)]
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    def to_config(self) -> HttpServerConfig:
        return HttpServerConfig(
            url=self.url,
            headers=self.headers,
            enabled=self.enabled,
        )


ServerBody = StdioServerBody | HttpServerBody


class CreateServerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1)]
    server: ServerBody = Field(discriminator="transport")


class UpdateServerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server: ServerBody = Field(discriminator="transport")


class ServerStatusResponse(BaseModel):
    """Live runner state plus the saved config from ``mcp.json``."""

    name: str
    transport: str
    enabled: bool
    state: str
    error: str | None = None
    tool_names: list[str] = Field(default_factory=list)
    started_at: str | None = None
    config: ServerBody | None = Field(default=None, discriminator="transport")


class ServerListResponse(BaseModel):
    servers: list[ServerStatusResponse]


class ServerDeleteResponse(BaseModel):
    name: str
