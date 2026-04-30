"""Adapter that wraps an MCP server tool as a local :class:`Tool`.

An MCP tool ships with a JSON Schema (``inputSchema``) for its arguments.
We forward that schema directly to the LLM in the OpenAI-compatible
function-calling shape, and route invocations back through the live
``ClientSession`` held by the :class:`MCPManager`.

Tool names follow the convention ``mcp_<server>_<tool>`` so they are easy
to gate via the existing permission system (``mcp_*`` wildcard) and never
collide with built-in tool names.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import BaseModel

from app.agent.errors import ToolExecutionError
from app.agent.tools.registry import Tool

if TYPE_CHECKING:
    from mcp import ClientSession
    from mcp.types import Tool as MCPToolDef


def _sanitize_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Coerce an MCP tool ``inputSchema`` into the OpenAI function-call shape.

    MCP servers return JSON Schema; OpenAI tool schemas are JSON Schema with
    a ``type: "object"`` wrapper. Most servers already return that shape.
    """
    if not schema or not isinstance(schema, dict):
        return {"type": "object", "properties": {}, "required": []}

    result = dict(schema)
    result.setdefault("type", "object")
    result.setdefault("properties", {})
    # ``required`` is optional in JSON Schema but expected by some providers.
    result.setdefault("required", [])
    # Drop $schema / $id metadata that some servers include — providers reject it.
    result.pop("$schema", None)
    result.pop("$id", None)
    return result


class _NoopParameters(BaseModel):
    """Placeholder Pydantic model — MCPTool does not use base-class validation."""

    model_config = {"extra": "allow"}


class MCPTool(Tool):
    """A :class:`Tool` whose schema and execution are sourced from an MCP server.

    Unlike the base ``Tool``, the JSON Schema comes from the MCP server's
    ``inputSchema`` rather than being derived from a Python function signature.
    Calls are forwarded to ``session.call_tool(remote_name, args)``.
    """

    def __init__(
        self,
        *,
        server_name: str,
        mcp_tool: "MCPToolDef",
        session_provider: "_SessionProvider",
    ) -> None:
        self._server_name = server_name
        self._remote_name = mcp_tool.name
        self._session_provider = session_provider

        local_name = f"mcp_{server_name}_{mcp_tool.name}"
        description = (
            mcp_tool.description
            or f"Tool '{mcp_tool.name}' from MCP server '{server_name}'."
        )

        # ── Build the OpenAI-compatible tool definition directly ─────────
        parameters = _sanitize_schema(
            mcp_tool.inputSchema if hasattr(mcp_tool, "inputSchema") else None
        )
        self._definition = {
            "type": "function",
            "function": {
                "name": local_name,
                "description": description,
                "parameters": parameters,
            },
        }
        self._model = _NoopParameters
        self._injected_params: set[str] = set()

        self.name = local_name
        self._custom_description = description
        self._func = self._invoke  # for repr / __wrapped__ compatibility

        self.__name__ = local_name
        self.__doc__ = description
        self.__wrapped__ = self._invoke

    async def arun(self, _injected: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Forward the call to the MCP server.

        ``_injected`` is accepted for interface compatibility with builtins
        but unused — MCP tools cannot consume :class:`AgentState`.
        """
        del _injected  # unused
        return await self._invoke(**kwargs)

    async def _invoke(self, **kwargs: Any) -> str:
        session = self._session_provider()
        if session is None:
            raise ToolExecutionError(
                f"MCP server '{self._server_name}' is not connected."
            )

        logger.debug(
            "mcp_tool_call server={} tool={} args={}",
            self._server_name,
            self._remote_name,
            list(kwargs.keys()),
        )
        try:
            result = await session.call_tool(self._remote_name, kwargs)
        except Exception as exc:
            raise ToolExecutionError(
                f"MCP tool '{self.name}' failed: {type(exc).__name__}: {exc}"
            ) from exc

        if getattr(result, "isError", False):
            text = _extract_text(result.content)
            raise ToolExecutionError(
                f"MCP tool '{self.name}' returned error: {text or '(no message)'}"
            )

        return _extract_text(result.content)


def _extract_text(content: Any) -> str:
    """Best-effort flatten an MCP ``CallToolResult.content`` list to a string.

    MCP content is a list of typed blocks (``TextContent``, ``ImageContent``,
    ``EmbeddedResource``). For now we only render ``TextContent`` and
    summarise the rest, since the agent loop already has rich multimodal
    handling and we don't want to leak base64 image blobs back through here.
    """
    if not content:
        return ""
    if not isinstance(content, list):
        return str(content)

    parts: list[str] = []
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            parts.append(getattr(block, "text", "") or "")
        elif block_type == "image":
            mime = getattr(block, "mimeType", "image/*")
            parts.append(f"[image: {mime}]")
        elif block_type == "resource":
            uri = getattr(getattr(block, "resource", None), "uri", "?")
            parts.append(f"[resource: {uri}]")
        else:
            parts.append(str(block))
    return "\n".join(parts)


# ── Type alias for the session-resolution callback ──────────────────────────
# Defined at module bottom to avoid a forward reference in MCPTool.__init__.

from typing import Callable, Optional  # noqa: E402

_SessionProvider = Callable[[], Optional["ClientSession"]]
