"""Tests for app/providers/streaming.py — iter_sse_data."""

import json
import pytest

from app.agent.providers.streaming import iter_sse_data


class _MockResponse:
    """Minimal async line iterator."""

    def __init__(self, lines: list[str]):
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


async def _collect(response, **kwargs) -> list[dict]:
    results = []
    async for item in iter_sse_data(response, **kwargs):
        results.append(item)
    return results


@pytest.mark.asyncio
async def test_iter_sse_data_basic():
    data = {"id": "1", "text": "hello"}
    resp = _MockResponse([f"data: {json.dumps(data)}"])
    results = await _collect(resp, sentinel=None)
    assert results == [data]


@pytest.mark.asyncio
async def test_iter_sse_data_sentinel_stops_iteration():
    data = {"id": "1"}
    resp = _MockResponse(
        [
            f"data: {json.dumps(data)}",
            "data: [DONE]",
            "data: should_not_appear",
        ]
    )
    results = await _collect(resp)
    assert len(results) == 1
    assert results[0] == data


@pytest.mark.asyncio
async def test_iter_sse_data_skips_non_data_lines():
    data = {"ok": True}
    resp = _MockResponse(
        [
            "event: update",
            "id: 42",
            "",
            f"data: {json.dumps(data)}",
        ]
    )
    results = await _collect(resp, sentinel=None)
    assert results == [data]


@pytest.mark.asyncio
async def test_iter_sse_data_skips_invalid_json():
    valid = {"v": 1}
    resp = _MockResponse(
        [
            "data: not_valid_json{{{",
            f"data: {json.dumps(valid)}",
        ]
    )
    results = await _collect(resp, sentinel=None)
    assert results == [valid]


@pytest.mark.asyncio
async def test_iter_sse_data_empty_stream():
    resp = _MockResponse([])
    results = await _collect(resp)
    assert results == []


@pytest.mark.asyncio
async def test_iter_sse_data_custom_sentinel():
    data = {"x": 1}
    resp = _MockResponse(
        [
            f"data: {json.dumps(data)}",
            "data: END",
            "data: after",
        ]
    )
    results = await _collect(resp, sentinel="END")
    assert results == [data]


@pytest.mark.asyncio
async def test_iter_sse_data_multiple_items():
    items = [{"n": i} for i in range(5)]
    lines = [f"data: {json.dumps(item)}" for item in items]
    resp = _MockResponse(lines)
    results = await _collect(resp, sentinel=None)
    assert results == items
