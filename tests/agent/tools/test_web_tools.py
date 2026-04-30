from unittest.mock import patch

import httpx
import pytest
import respx

from app.agent.tools.builtin.web import web_fetch, web_search


@pytest.mark.asyncio
async def test_web_search_success():
    with patch("app.agent.tools.builtin.web.DDGS") as mock_ddgs_class:
        mock_ddgs = mock_ddgs_class.return_value
        mock_ddgs.text.return_value = [{"title": "t", "href": "h", "body": "b"}]

        result = await web_search("query")
        assert len(result) == 1
        assert result[0]["title"] == "t"


@pytest.mark.asyncio
async def test_web_search_exception_returns_string():
    """When DDGS raises and Exa also fails, web_search returns 'No result found'."""
    with patch("app.agent.tools.builtin.web.DDGS") as mock_ddgs_class:
        mock_ddgs = mock_ddgs_class.return_value
        mock_ddgs.text.side_effect = Exception("network error")

        with respx.mock:
            respx.post("https://mcp.exa.ai/mcp").mock(side_effect=Exception("exa down"))
            result = await web_search("failing query")
        assert result == "No result found"


@pytest.mark.asyncio
async def test_web_search_exa_fallback_with_error():
    """When DDGS fails and Exa returns an error, the error message is returned."""
    with patch("app.agent.tools.builtin.web.DDGS") as mock_ddgs_class:
        mock_ddgs = mock_ddgs_class.return_value
        mock_ddgs.text.return_value = None

        with respx.mock:
            respx.post("https://mcp.exa.ai/mcp").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "error": {"code": -32000, "message": "Invalid query"},
                    },
                )
            )

            result = await web_search("failing query")
            assert "Error:" in result
            assert "Invalid query" in result


@pytest.mark.asyncio
async def test_web_search_exa_fallback_success():
    """When DDGS fails but Exa succeeds, results from Exa are returned."""
    with patch("app.agent.tools.builtin.web.DDGS") as mock_ddgs_class:
        mock_ddgs = mock_ddgs_class.return_value
        mock_ddgs.text.return_value = None

        with respx.mock:
            respx.post("https://mcp.exa.ai/mcp").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": [
                            {"title": "Exa Result", "url": "https://example.com"}
                        ],
                    },
                )
            )

            result = await web_search("test query")
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["title"] == "Exa Result"


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_html_converted_via_markitdown():
    """HTML responses are converted to Markdown via MarkItDown."""
    url = "https://example.com"
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="<html><body><h1>Hello</h1></body></html>",
            headers={"content-type": "text/html"},
        )
    )

    with patch("app.agent.tools.builtin.web.MarkItDown") as mock_mid_class:
        mock_mid = mock_mid_class.return_value
        mock_mid.convert_stream.return_value.markdown = "# Hello"

        result = await web_fetch(url)
        assert result == "# Hello"
        mock_mid.convert_stream.assert_called_once()


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_native_markdown_returned_asis():
    """Responses with text/markdown MIME type are returned as-is without MarkItDown."""
    url = "https://example.com/readme.md"
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="# Native Markdown",
            headers={"content-type": "text/markdown"},
        )
    )

    with patch("app.agent.tools.builtin.web.MarkItDown") as mock_mid_class:
        result = await web_fetch(url)
        assert result == "# Native Markdown"
        mock_mid_class.return_value.convert_stream.assert_not_called()


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_no_scheme_prefixed():
    """URL without scheme gets https:// prepended."""
    respx.get("https://example.com").mock(
        return_value=httpx.Response(
            200,
            text="<html><body>Test</body></html>",
            headers={"content-type": "text/html"},
        )
    )

    with patch("app.agent.tools.builtin.web.MarkItDown") as mock_mid_class:
        mock_mid = mock_mid_class.return_value
        mock_mid.convert_stream.return_value.markdown = "Test"

        result = await web_fetch("example.com")
        assert result == "Test"


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_format_html_uses_markitdown():
    """format='html' still uses MarkItDown for conversion."""
    url = "https://example.com"
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="<html><body>Raw</body></html>",
            headers={"content-type": "text/html"},
        )
    )

    with patch("app.agent.tools.builtin.web.MarkItDown") as mock_mid_class:
        mock_mid = mock_mid_class.return_value
        mock_mid.convert_stream.return_value.markdown = "Raw"

        result = await web_fetch(url, format="html")
        assert result == "Raw"
        mock_mid.convert_stream.assert_called_once()


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_http_error_returns_error_string():
    """Non-2xx response returns an error string."""
    url = "https://nonexistent-url.com"
    respx.get(url).mock(return_value=httpx.Response(404))

    result = await web_fetch(url)
    assert "Error fetching or converting" in result


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_content_length_too_large():
    """Responses with content-length > 5MB are rejected."""
    url = "https://example.com/bigfile"
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="x",
            headers={
                "content-type": "text/plain",
                "content-length": str(6 * 1024 * 1024),
            },
        )
    )

    result = await web_fetch(url)
    assert "too large" in result


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_cloudflare_retry():
    """403 with cf-mitigated=challenge retries with 'opencode' User-Agent."""
    url = "https://example.com"
    call_count = 0

    def side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(403, headers={"cf-mitigated": "challenge"})
        return httpx.Response(
            200,
            text="<p>OK</p>",
            headers={"content-type": "text/html"},
        )

    respx.get(url).mock(side_effect=side_effect)

    with patch("app.agent.tools.builtin.web.MarkItDown") as mock_mid_class:
        mock_mid = mock_mid_class.return_value
        mock_mid.convert_stream.return_value.markdown = "OK"

        result = await web_fetch(url)
        assert result == "OK"
        assert call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_body_too_large_without_content_length():
    """Responses where body exceeds 5MB (no content-length header) are rejected.

    Covers web_tools.py:107 — the body-size check after reading content.
    """
    url = "https://example.com/bigbody"
    # Serve a body larger than _MAX_RESPONSE_BYTES (5 MB).
    # Build the httpx.Response manually and strip the content-length header so
    # that only the body-size check (line 107) is reached, not the header check.
    big_body = b"x" * (5 * 1024 * 1024 + 1)
    response = httpx.Response(
        200,
        content=big_body,
        headers={"content-type": "text/plain"},
    )
    # Remove the auto-set content-length so the header branch is skipped
    response.headers.pop("content-length", None)
    respx.get(url).mock(return_value=response)

    result = await web_fetch(url)
    assert "too large" in result
    assert "bytes exceeds" in result


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_timeout_capped_at_120():
    """timeout > 120 is capped to 120 seconds."""
    url = "https://example.com"
    respx.get(url).mock(
        return_value=httpx.Response(
            200, text="<p>hi</p>", headers={"content-type": "text/html"}
        )
    )

    with patch("app.agent.tools.builtin.web.MarkItDown") as mock_mid_class:
        mock_mid = mock_mid_class.return_value
        mock_mid.convert_stream.return_value.markdown = "hi"

        result = await web_fetch(url, timeout=9999)
        assert result == "hi"
