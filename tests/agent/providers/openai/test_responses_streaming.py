"""Tests for `ResponsesHandler` SSE streaming parser — event sequences,
text deltas, tool-call assembly, reasoning chunks, and edge cases.

See `app/agent/providers/openai/responses.py:ResponsesHandler.parse_stream`.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agent.providers.openai.responses import ResponsesHandler


# ─────────────────────────────────────────────────────────────────────────────
# Test ResponsesHandler streaming parser
# ─────────────────────────────────────────────────────────────────────────────


class TestResponsesStreaming:
    """Test Responses API streaming parser."""

    @pytest.fixture
    def handler(self):
        """Create a ResponsesHandler instance."""
        return ResponsesHandler(
            model="gpt-5.4",
            base_url="https://api.openai.com/v1",
            headers={"Authorization": "Bearer sk-test"},
        )

    async def test_parse_stream_text_response(self, handler):
        """Parse streaming text response."""
        # Each event is split into separate lines (event: and data:)
        lines = [
            "event: response.created",
            'data: {"type": "response.created", "response": {"id": "resp_123"}}',
            "event: response.output_text.delta",
            'data: {"type": "response.output_text.delta", "delta": "Hello"}',
            "event: response.output_text.delta",
            'data: {"type": "response.output_text.delta", "delta": " world"}',
            "event: response.output_text.done",
            'data: {"type": "response.output_text.done"}',
            "event: response.completed",
            'data: {"type": "response.completed", "response": {"id": "resp_123", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}}',
        ]

        # Mock response object with async iterator
        async def async_iter_lines():
            for line in lines:
                yield line

        response = MagicMock()
        response.aiter_lines = lambda: async_iter_lines()

        chunks = []
        async for chunk in handler._parse_stream(response):
            chunks.append(chunk)

        # Should have 4 chunks: 2 text deltas + 1 done + 1 usage
        assert len(chunks) == 4
        assert chunks[0].choices[0].delta.content == "Hello"
        assert chunks[1].choices[0].delta.content == " world"
        assert chunks[2].choices[0].finish_reason == "stop"
        assert chunks[3].usage is not None
        assert chunks[3].usage.prompt_tokens == 10
        assert chunks[3].usage.completion_tokens == 5

    async def test_parse_stream_tool_call(self, handler):
        """Parse streaming tool call response."""
        lines = [
            "event: response.created",
            'data: {"type": "response.created", "response": {"id": "resp_123"}}',
            "event: response.output_item.added",
            'data: {"type": "response.output_item.added", "item": {"id": "fc_456", "type": "function_call", "name": "get_weather"}}',
            "event: response.function_call_arguments.delta",
            'data: {"type": "response.function_call_arguments.delta", "item_id": "fc_456", "delta": "{\\"city"}',
            "event: response.function_call_arguments.delta",
            'data: {"type": "response.function_call_arguments.delta", "item_id": "fc_456", "delta": "\\": \\"NYC\\"}"}',
            "event: response.function_call_arguments.done",
            'data: {"type": "response.function_call_arguments.done", "item_id": "fc_456", "arguments": "{\\"city\\": \\"NYC\\"}"}',
            "event: response.completed",
            'data: {"type": "response.completed", "response": {"id": "resp_123", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}}',
        ]

        async def async_iter_lines():
            for line in lines:
                yield line

        response = MagicMock()
        response.aiter_lines = lambda: async_iter_lines()

        chunks = []
        async for chunk in handler._parse_stream(response):
            chunks.append(chunk)

        # Should have 4 chunks: 2 arg deltas + 1 done + 1 usage
        assert len(chunks) == 4
        # First two chunks are argument deltas
        assert chunks[0].choices[0].delta.tool_calls is not None
        assert chunks[0].choices[0].delta.tool_calls[0].function.arguments == '{"city'
        assert (
            chunks[1].choices[0].delta.tool_calls[0].function.arguments == '": "NYC"}'
        )
        # Third chunk is the done event with function name
        assert chunks[2].choices[0].delta.tool_calls[0].function.name == "get_weather"
        assert chunks[2].choices[0].delta.tool_calls[0].id == "fc_456"

    async def test_parse_stream_reasoning_and_text(self, handler):
        """Parse streaming response with reasoning and text."""
        lines = [
            "event: response.created",
            'data: {"type": "response.created", "response": {"id": "resp_123"}}',
            "event: response.reasoning_summary_text.delta",
            'data: {"type": "response.reasoning_summary_text.delta", "delta": "Let me think"}',
            "event: response.output_text.delta",
            'data: {"type": "response.output_text.delta", "delta": "The answer"}',
            "event: response.output_text.done",
            'data: {"type": "response.output_text.done"}',
            "event: response.completed",
            'data: {"type": "response.completed", "response": {"id": "resp_123", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}}',
        ]

        async def async_iter_lines():
            for line in lines:
                yield line

        response = MagicMock()
        response.aiter_lines = lambda: async_iter_lines()

        chunks = []
        async for chunk in handler._parse_stream(response):
            chunks.append(chunk)

        # Should have 4 chunks: 1 reasoning + 1 text + 1 done + 1 usage
        assert len(chunks) == 4
        assert chunks[0].choices[0].delta.reasoning_content == "Let me think"
        assert chunks[1].choices[0].delta.content == "The answer"

    async def test_parse_stream_skips_invalid_json(self, handler):
        """Skip lines with invalid JSON."""
        lines = [
            "event: response.created",
            'data: {"type": "response.created", "response": {"id": "resp_123"}}',
            "event: response.output_text.delta",
            "data: {invalid json}",
            "event: response.output_text.delta",
            'data: {"type": "response.output_text.delta", "delta": "Hello"}',
            "event: response.output_text.done",
            'data: {"type": "response.output_text.done"}',
            "event: response.completed",
            'data: {"type": "response.completed", "response": {"id": "resp_123", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}}',
        ]

        async def async_iter_lines():
            for line in lines:
                yield line

        response = MagicMock()
        response.aiter_lines = lambda: async_iter_lines()

        chunks = []
        async for chunk in handler._parse_stream(response):
            chunks.append(chunk)

        # Should skip the invalid JSON line
        assert len(chunks) == 3
        assert chunks[0].choices[0].delta.content == "Hello"

    async def test_parse_stream_stops_at_done_sentinel(self, handler):
        """Stop parsing at [DONE] sentinel."""
        lines = [
            "event: response.created",
            'data: {"type": "response.created", "response": {"id": "resp_123"}}',
            "event: response.output_text.delta",
            'data: {"type": "response.output_text.delta", "delta": "Hello"}',
            "data: [DONE]",
            "event: response.output_text.delta",
            'data: {"type": "response.output_text.delta", "delta": " world"}',
        ]

        async def async_iter_lines():
            for line in lines:
                yield line

        response = MagicMock()
        response.aiter_lines = lambda: async_iter_lines()

        chunks = []
        async for chunk in handler._parse_stream(response):
            chunks.append(chunk)

        # Should stop at [DONE], so only 1 text chunk
        assert len(chunks) == 1
        assert chunks[0].choices[0].delta.content == "Hello"

    async def test_parse_stream_multiple_tool_calls(self, handler):
        """Parse streaming response with multiple tool calls."""
        lines = [
            "event: response.created",
            'data: {"type": "response.created", "response": {"id": "resp_123"}}',
            "event: response.output_item.added",
            'data: {"type": "response.output_item.added", "item": {"id": "fc_1", "type": "function_call", "name": "tool_a"}}',
            "event: response.function_call_arguments.delta",
            'data: {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": "{\\"x"}',
            "event: response.output_item.added",
            'data: {"type": "response.output_item.added", "item": {"id": "fc_2", "type": "function_call", "name": "tool_b"}}',
            "event: response.function_call_arguments.delta",
            'data: {"type": "response.function_call_arguments.delta", "item_id": "fc_2", "delta": "{\\"y"}',
            "event: response.function_call_arguments.done",
            'data: {"type": "response.function_call_arguments.done", "item_id": "fc_1", "arguments": "{\\"x\\": 1}"}',
            "event: response.function_call_arguments.done",
            'data: {"type": "response.function_call_arguments.done", "item_id": "fc_2", "arguments": "{\\"y\\": 2}"}',
            "event: response.completed",
            'data: {"type": "response.completed", "response": {"id": "resp_123", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}}',
        ]

        async def async_iter_lines():
            for line in lines:
                yield line

        response = MagicMock()
        response.aiter_lines = lambda: async_iter_lines()

        chunks = []
        async for chunk in handler._parse_stream(response):
            chunks.append(chunk)

        # Should have 5 chunks: 2 arg deltas + 2 done + 1 usage
        assert len(chunks) == 5
        # First delta is for fc_1 (index 0)
        assert chunks[0].choices[0].delta.tool_calls[0].index == 0
        assert chunks[0].choices[0].delta.tool_calls[0].id == "fc_1"
        # Second delta is for fc_2 (index 1)
        assert chunks[1].choices[0].delta.tool_calls[0].index == 1
        assert chunks[1].choices[0].delta.tool_calls[0].id == "fc_2"


# ─────────────────────────────────────────────────────────────────────────────
# Test OpenAIProvider routing
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Test ResponsesHandler._parse_stream() edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestResponsesStreamingEdgeCases:
    """Test ResponsesHandler streaming parser edge cases."""

    @pytest.fixture
    def handler(self):
        """Create a ResponsesHandler instance."""
        return ResponsesHandler(
            model="gpt-5.4",
            base_url="https://api.openai.com/v1",
            headers={"Authorization": "Bearer sk-test"},
        )

    async def test_parse_stream_done_event_before_delta(self, handler):
        """Test done event arriving before any delta event for that call_id."""
        lines = [
            "event: response.created",
            'data: {"type": "response.created", "response": {"id": "resp_123"}}',
            "event: response.output_item.added",
            'data: {"type": "response.output_item.added", "item": {"id": "fc_456", "type": "function_call", "name": "get_weather"}}',
            "event: response.function_call_arguments.done",
            'data: {"type": "response.function_call_arguments.done", "item_id": "fc_456", "arguments": "{\\"city\\": \\"NYC\\"}"}',
            "event: response.completed",
            'data: {"type": "response.completed", "response": {"id": "resp_123", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}}',
        ]

        async def async_iter_lines():
            for line in lines:
                yield line

        response = MagicMock()
        response.aiter_lines = lambda: async_iter_lines()

        chunks = []
        async for chunk in handler._parse_stream(response):
            chunks.append(chunk)

        # Should have 2 chunks: 1 done + 1 usage
        assert len(chunks) == 2
        # The done event should create a tool call with the function name
        assert chunks[0].choices[0].delta.tool_calls is not None
        assert chunks[0].choices[0].delta.tool_calls[0].function.name == "get_weather"
        assert chunks[0].choices[0].delta.tool_calls[0].id == "fc_456"

    async def test_parse_stream_skips_lines_without_data_prefix(self, handler):
        """Test that lines without 'data: ' prefix are skipped."""
        lines = [
            "event: response.created",
            'data: {"type": "response.created", "response": {"id": "resp_123"}}',
            "some random line without data prefix",
            "event: response.output_text.delta",
            'data: {"type": "response.output_text.delta", "delta": "Hello"}',
            "event: response.output_text.done",
            'data: {"type": "response.output_text.done"}',
            "event: response.completed",
            'data: {"type": "response.completed", "response": {"id": "resp_123", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}}',
        ]

        async def async_iter_lines():
            for line in lines:
                yield line

        response = MagicMock()
        response.aiter_lines = lambda: async_iter_lines()

        chunks = []
        async for chunk in handler._parse_stream(response):
            chunks.append(chunk)

        # Should have 3 chunks: 1 text + 1 done + 1 usage (random line skipped)
        assert len(chunks) == 3
        assert chunks[0].choices[0].delta.content == "Hello"

    async def test_parse_stream_multiple_tool_calls_first_seen_in_done(self, handler):
        """Test multiple tool calls where one is first seen in done event."""
        lines = [
            "event: response.created",
            'data: {"type": "response.created", "response": {"id": "resp_123"}}',
            "event: response.output_item.added",
            'data: {"type": "response.output_item.added", "item": {"id": "fc_1", "type": "function_call", "name": "tool_a"}}',
            "event: response.function_call_arguments.delta",
            'data: {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": "{\\"x"}',
            "event: response.function_call_arguments.done",
            'data: {"type": "response.function_call_arguments.done", "item_id": "fc_1", "arguments": "{\\"x\\": 1}"}',
            "event: response.output_item.added",
            'data: {"type": "response.output_item.added", "item": {"id": "fc_2", "type": "function_call", "name": "tool_b"}}',
            "event: response.function_call_arguments.done",
            'data: {"type": "response.function_call_arguments.done", "item_id": "fc_2", "arguments": "{\\"y\\": 2}"}',
            "event: response.completed",
            'data: {"type": "response.completed", "response": {"id": "resp_123", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}}',
        ]

        async def async_iter_lines():
            for line in lines:
                yield line

        response = MagicMock()
        response.aiter_lines = lambda: async_iter_lines()

        chunks = []
        async for chunk in handler._parse_stream(response):
            chunks.append(chunk)

        # Should have 4 chunks: 1 delta + 2 done + 1 usage
        assert len(chunks) == 4
        # First chunk is the delta for fc_1
        assert chunks[0].choices[0].delta.tool_calls[0].index == 0
        assert chunks[0].choices[0].delta.tool_calls[0].id == "fc_1"
        # Second chunk is the done for fc_1
        assert chunks[1].choices[0].delta.tool_calls[0].index == 0
        # Third chunk is the done for fc_2 (first seen in done, so index 1)
        assert chunks[2].choices[0].delta.tool_calls[0].index == 1
        assert chunks[2].choices[0].delta.tool_calls[0].id == "fc_2"


# ─────────────────────────────────────────────────────────────────────────────
# Test OpenAIProvider.chat() and stream() delegation
# ─────────────────────────────────────────────────────────────────────────────
