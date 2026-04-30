import asyncio
from io import BytesIO
from typing import Annotated, Any, Literal

import httpx
from ddgs import DDGS
from loguru import logger
from markitdown import MarkItDown, StreamInfo
from pydantic import Field

from app.agent.tools.registry import tool

_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB
_DEFAULT_TIMEOUT = 30.0
_MAX_TIMEOUT = 120.0

_ACCEPT_HEADERS: dict[str, str] = {
    "markdown": "text/markdown;q=1.0, text/x-markdown;q=0.9, text/plain;q=0.8, text/html;q=0.7, */*;q=0.1",
    "html": "text/html;q=1.0, application/xhtml+xml;q=0.9, text/plain;q=0.8, */*;q=0.1",
    "text": "text/plain;q=1.0, text/html;q=0.9, */*;q=0.1",
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/143.0.0.0 Safari/537.36"
)


@tool(name="web_search")
async def web_search(
    query: Annotated[
        str,
        Field(description="Search query string."),
    ],
    max_results: Annotated[
        int,
        Field(description="Number of results (default 5, max 20)."),
    ] = 5,
    page: Annotated[
        int,
        Field(description="Page number (default 1)."),
    ] = 1,
    safesearch: Annotated[
        Literal["on", "moderate", "off"],
        Field(description="Safe search level (default 'moderate')."),
    ] = "moderate",
) -> list[dict[str, Any]] | str:
    """Search the web. Returns [{title, href, body}]."""
    try:
        results = DDGS().text(
            query, max_results=max_results, page=page, safesearch=safesearch
        )
    except Exception as e:
        logger.debug(f"Error during web search: {str(e)}")
        results = None

    if results:
        return results

    logger.debug(
        "DDGS search failed or returned no results, falling back to Exa search"
    )
    # Fallback to Exa search tool if DDGS fails or returns no results
    url = "https://mcp.exa.ai/mcp"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search",
            "arguments": {"query": query, "numResults": max_results},
        },
    }
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            if "error" in result:
                logger.debug(f"Exa search error: {result['error']}")
                return f"Error: {result['error']}"
            return result.get("result", [])
    except Exception as e:
        logger.debug(f"Error during Exa search: {str(e)}")
        return "No result found"


@tool(name="web_fetch")
async def web_fetch(
    url: Annotated[
        str,
        Field(description="URL to fetch. https:// prepended if no scheme."),
    ],
    format: Annotated[  # noqa: A002
        Literal["markdown", "html", "text"],
        Field(description="Response format (default 'markdown')."),
    ] = "markdown",
    timeout: Annotated[
        int | None,
        Field(description="Timeout in seconds (default 30, max 120)."),
    ] = None,
) -> str:
    """Fetch a URL and return its content. Handles HTML, PDF, and plain text."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    timeout_s = min(float(timeout) if timeout else _DEFAULT_TIMEOUT, _MAX_TIMEOUT)

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": _ACCEPT_HEADERS[format],
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(
            follow_redirects=True, verify=True, timeout=timeout_s
        ) as client:
            response = await client.get(url, headers=headers)

            # Cloudflare bot-detection retry with honest UA
            if (
                response.status_code == 403
                and response.headers.get("cf-mitigated") == "challenge"
            ):
                logger.debug("web_fetch_cloudflare_retry url={}", url)
                response = await client.get(
                    url, headers={**headers, "User-Agent": "opencode"}
                )

            response.raise_for_status()

            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > _MAX_RESPONSE_BYTES:
                return f"Error: Response too large (content-length {content_length} exceeds 5 MB limit)"

            content_bytes = response.content
            if len(content_bytes) > _MAX_RESPONSE_BYTES:
                return f"Error: Response too large ({len(content_bytes)} bytes exceeds 5 MB limit)"

            content_type = response.headers.get("content-type", "")

        mime = content_type.split(";")[0].strip().lower() or None

        # If the response is already markdown, return it as-is
        if mime in ("text/markdown", "text/x-markdown"):
            return content_bytes.decode("utf-8", errors="replace")

        # For all other types (html, text, pdf, etc.) let MarkItDown convert
        def _convert() -> str:
            md = MarkItDown()
            result = md.convert_stream(
                BytesIO(content_bytes),
                stream_info=StreamInfo(url=url, mimetype=mime),
            )
            return result.markdown

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _convert)

    except Exception as e:
        return f"Error fetching or converting: {str(e)}"
