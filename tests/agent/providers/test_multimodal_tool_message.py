"""Tests for multimodal ToolMessage conversion in all providers.

Tests that each provider correctly converts a ToolMessage with parts
(from ToolResult-returning tools) into their wire format.

Covers:
- OpenAI provider: ToolMessage with parts → content array with image_url/text
- Copilot provider: same as OpenAI (shared format)
- Gemini provider: ToolMessage with parts → Content with FunctionResponse + Parts
- ZAI provider: ToolMessage with parts → dict with content array
"""

from __future__ import annotations

import base64

import pytest

from app.agent.providers.copilot.copilot import CopilotProvider
from app.agent.providers.googlegenai.googlegenai import GoogleGenAIProvider
from app.agent.providers.openai.completions import CompletionsHandler
from app.agent.providers.zai.zai import ZAIProvider
from app.agent.schemas.chat import (
    ImageDataBlock,
    ImageUrlBlock,
    TextBlock,
    ToolMessage,
)


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI Provider Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestOpenAIMultimodalToolMessage:
    """OpenAI CompletionsHandler converts ToolMessage.parts to content array."""

    @pytest.fixture
    def handler(self):
        return CompletionsHandler(
            model="gpt-4o",
            base_url="https://api.openai.com/v1",
            headers={"Authorization": "Bearer sk-test"},
        )

    def test_tool_message_with_text_block(self, handler: CompletionsHandler):
        """ToolMessage with TextBlock → content array with text type."""
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            parts=[TextBlock(text="File contents here")],
        )
        converted = handler.convert_messages([msg])

        assert len(converted) == 1
        assert converted[0].role == "tool"
        assert converted[0].tool_call_id == "call_1"
        assert converted[0].name == "read_file"
        # Content should be an array with text object
        assert isinstance(converted[0].content, list)
        assert len(converted[0].content) == 1
        assert converted[0].content[0]["type"] == "text"
        assert converted[0].content[0]["text"] == "File contents here"

    def test_tool_message_with_image_data_block(self, handler: CompletionsHandler):
        """ToolMessage with ImageDataBlock → content array with image_url type."""
        img_data = base64.b64encode(b"fake_image_data").decode("ascii")
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            parts=[ImageDataBlock(data=img_data, media_type="image/png")],
        )
        converted = handler.convert_messages([msg])

        assert len(converted) == 1
        assert isinstance(converted[0].content, list)
        assert len(converted[0].content) == 1
        assert converted[0].content[0]["type"] == "image_url"
        assert "image_url" in converted[0].content[0]
        img_url = converted[0].content[0]["image_url"]
        assert img_url["url"].startswith("data:image/png;base64,")
        assert img_url["detail"] == "auto"

    def test_tool_message_with_image_url_block(self, handler: CompletionsHandler):
        """ToolMessage with ImageUrlBlock → content array with image_url type."""
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            parts=[ImageUrlBlock(url="https://example.com/image.jpg")],
        )
        converted = handler.convert_messages([msg])

        assert len(converted) == 1
        assert isinstance(converted[0].content, list)
        assert len(converted[0].content) == 1
        assert converted[0].content[0]["type"] == "image_url"
        img_url = converted[0].content[0]["image_url"]
        assert img_url["url"] == "https://example.com/image.jpg"

    def test_tool_message_with_mixed_parts(self, handler: CompletionsHandler):
        """ToolMessage with mixed TextBlock and ImageDataBlock → content array."""
        img_data = base64.b64encode(b"fake_image").decode("ascii")
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            parts=[
                TextBlock(text="Here is the image:"),
                ImageDataBlock(data=img_data, media_type="image/jpeg"),
            ],
        )
        converted = handler.convert_messages([msg])

        assert len(converted) == 1
        assert isinstance(converted[0].content, list)
        assert len(converted[0].content) == 2
        assert converted[0].content[0]["type"] == "text"
        assert converted[0].content[0]["text"] == "Here is the image:"
        assert converted[0].content[1]["type"] == "image_url"

    def test_tool_message_without_parts_backward_compat(
        self, handler: CompletionsHandler
    ):
        """ToolMessage without parts (None) → plain string content (backward compat)."""
        msg = ToolMessage(
            content="Plain text result",
            tool_call_id="call_1",
            name="read_file",
            parts=None,
        )
        converted = handler.convert_messages([msg])

        assert len(converted) == 1
        assert converted[0].role == "tool"
        assert converted[0].content == "Plain text result"
        assert isinstance(converted[0].content, str)


# ─────────────────────────────────────────────────────────────────────────────
# Copilot Provider Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCopilotMultimodalToolMessage:
    """Copilot provider converts ToolMessage.parts to content array (same as OpenAI)."""

    @pytest.fixture
    def provider(self):
        return CopilotProvider(model="gpt-5-mini", github_token="gho_test_token")

    def test_tool_message_with_text_block(self, provider: CopilotProvider):
        """ToolMessage with TextBlock → content array with text type."""
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            parts=[TextBlock(text="File contents here")],
        )
        converted = provider._completions.convert_messages([msg])

        assert len(converted) == 1
        assert converted[0].role == "tool"
        assert isinstance(converted[0].content, list)
        assert len(converted[0].content) == 1
        assert converted[0].content[0]["type"] == "text"
        assert converted[0].content[0]["text"] == "File contents here"

    def test_tool_message_with_image_data_block(self, provider: CopilotProvider):
        """ToolMessage with ImageDataBlock → content array with image_url type."""
        img_data = base64.b64encode(b"fake_image_data").decode("ascii")
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            parts=[ImageDataBlock(data=img_data, media_type="image/png")],
        )
        converted = provider._completions.convert_messages([msg])

        assert len(converted) == 1
        assert isinstance(converted[0].content, list)
        assert len(converted[0].content) == 1
        assert converted[0].content[0]["type"] == "image_url"
        img_url = converted[0].content[0]["image_url"]
        assert img_url["url"].startswith("data:image/png;base64,")

    def test_tool_message_without_parts_backward_compat(
        self, provider: CopilotProvider
    ):
        """ToolMessage without parts (None) → plain string content."""
        msg = ToolMessage(
            content="Plain text result",
            tool_call_id="call_1",
            name="read_file",
            parts=None,
        )
        converted = provider._completions.convert_messages([msg])

        assert len(converted) == 1
        assert converted[0].content == "Plain text result"
        assert isinstance(converted[0].content, str)


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Provider Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGeminiMultimodalToolMessage:
    """Gemini provider converts ToolMessage.parts to Content with Parts."""

    @pytest.fixture
    def provider(self):
        return GoogleGenAIProvider(api_key="test_key", model="gemini-2.0-flash")

    def test_tool_message_with_text_block(self, provider: GoogleGenAIProvider):
        """ToolMessage with TextBlock → Content with FunctionResponse + text Part."""
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            content="File contents",
            parts=[TextBlock(text="Additional text from parts")],
        )
        contents, _ = provider._convert_messages_to_gemini([msg])

        assert len(contents) == 1
        content = contents[0]
        assert content.role == "user"
        assert len(content.parts) >= 2
        # First part should be FunctionResponse
        assert content.parts[0].function_response is not None
        assert content.parts[0].function_response.name == "read_file"
        # Second part should be text from parts
        assert content.parts[1].text == "Additional text from parts"

    def test_tool_message_with_image_data_block(self, provider: GoogleGenAIProvider):
        """ToolMessage with ImageDataBlock → Content with FunctionResponse + InlineData."""
        img_data = base64.b64encode(b"fake_image").decode("ascii")
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            content="Image result",
            parts=[ImageDataBlock(data=img_data, media_type="image/png")],
        )
        contents, _ = provider._convert_messages_to_gemini([msg])

        assert len(contents) == 1
        content = contents[0]
        assert content.role == "user"
        assert len(content.parts) >= 2
        # First part is FunctionResponse
        assert content.parts[0].function_response is not None
        # Second part is InlineData
        assert content.parts[1].inline_data is not None
        assert content.parts[1].inline_data.mime_type == "image/png"
        assert content.parts[1].inline_data.data == img_data

    def test_tool_message_with_image_url_block(self, provider: GoogleGenAIProvider):
        """ToolMessage with ImageUrlBlock → Content with FunctionResponse + FileData."""
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            content="Image result",
            parts=[ImageUrlBlock(url="https://example.com/image.jpg")],
        )
        contents, _ = provider._convert_messages_to_gemini([msg])

        assert len(contents) == 1
        content = contents[0]
        assert content.role == "user"
        assert len(content.parts) >= 2
        # First part is FunctionResponse
        assert content.parts[0].function_response is not None
        # Second part is FileData
        assert content.parts[1].file_data is not None
        assert content.parts[1].file_data.file_uri == "https://example.com/image.jpg"

    def test_tool_message_with_mixed_parts(self, provider: GoogleGenAIProvider):
        """ToolMessage with mixed parts → Content with FunctionResponse + multiple Parts."""
        img_data = base64.b64encode(b"fake_image").decode("ascii")
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            content="Result",
            parts=[
                TextBlock(text="Here is the image:"),
                ImageDataBlock(data=img_data, media_type="image/jpeg"),
            ],
        )
        contents, _ = provider._convert_messages_to_gemini([msg])

        assert len(contents) == 1
        content = contents[0]
        assert content.role == "user"
        # Should have FunctionResponse + text + image
        assert len(content.parts) >= 3
        assert content.parts[0].function_response is not None
        assert content.parts[1].text == "Here is the image:"
        assert content.parts[2].inline_data is not None

    def test_tool_message_without_parts_backward_compat(
        self, provider: GoogleGenAIProvider
    ):
        """ToolMessage without parts → Content with FunctionResponse only."""
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            content="Plain text result",
            parts=None,
        )
        contents, _ = provider._convert_messages_to_gemini([msg])

        assert len(contents) == 1
        content = contents[0]
        assert content.role == "user"
        # Should have only FunctionResponse
        assert len(content.parts) == 1
        assert content.parts[0].function_response is not None


# ─────────────────────────────────────────────────────────────────────────────
# ZAI Provider Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestZAIMultimodalToolMessage:
    """ZAI provider converts ToolMessage.parts to dict with content array.

    ZAI subclasses :class:`OpenAIProvider` so the conversion delegates to
    :class:`CompletionsHandler.convert_messages`. These tests exercise the
    real wiring on the provider instance to catch regressions if a future
    ``_ZAICompletionsHandler`` override ever forks the conversion path.
    """

    @pytest.fixture
    def provider(self):
        return ZAIProvider(api_key="test_key", model="claude-3-sonnet")

    @staticmethod
    def _serialize(provider: ZAIProvider, msg: ToolMessage) -> dict:
        handler: CompletionsHandler = provider._completions
        return handler.convert_messages([msg])[0].model_dump(exclude_none=True)

    def test_tool_message_with_text_block(self, provider: ZAIProvider):
        """ToolMessage with TextBlock → dict with content array."""
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            parts=[TextBlock(text="File contents here")],
        )
        serialized = self._serialize(provider, msg)

        assert serialized["role"] == "tool"
        assert serialized["tool_call_id"] == "call_1"
        assert serialized["name"] == "read_file"
        assert isinstance(serialized["content"], list)
        assert len(serialized["content"]) == 1
        assert serialized["content"][0]["type"] == "text"
        assert serialized["content"][0]["text"] == "File contents here"

    def test_tool_message_with_image_data_block(self, provider: ZAIProvider):
        """ToolMessage with ImageDataBlock → dict with content array."""
        img_data = base64.b64encode(b"fake_image_data").decode("ascii")
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            parts=[ImageDataBlock(data=img_data, media_type="image/png")],
        )
        serialized = self._serialize(provider, msg)

        assert serialized["role"] == "tool"
        assert isinstance(serialized["content"], list)
        assert len(serialized["content"]) == 1
        assert serialized["content"][0]["type"] == "image_url"
        img_url = serialized["content"][0]["image_url"]
        assert img_url["url"].startswith("data:image/png;base64,")
        assert img_url["detail"] == "auto"

    def test_tool_message_with_image_url_block(self, provider: ZAIProvider):
        """ToolMessage with ImageUrlBlock → dict with content array."""
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            parts=[ImageUrlBlock(url="https://example.com/image.jpg")],
        )
        serialized = self._serialize(provider, msg)

        assert serialized["role"] == "tool"
        assert isinstance(serialized["content"], list)
        assert len(serialized["content"]) == 1
        assert serialized["content"][0]["type"] == "image_url"
        img_url = serialized["content"][0]["image_url"]
        assert img_url["url"] == "https://example.com/image.jpg"

    def test_tool_message_with_mixed_parts(self, provider: ZAIProvider):
        """ToolMessage with mixed parts → dict with content array."""
        img_data = base64.b64encode(b"fake_image").decode("ascii")
        msg = ToolMessage(
            tool_call_id="call_1",
            name="read_file",
            parts=[
                TextBlock(text="Here is the image:"),
                ImageDataBlock(data=img_data, media_type="image/jpeg"),
            ],
        )
        serialized = self._serialize(provider, msg)

        assert serialized["role"] == "tool"
        assert isinstance(serialized["content"], list)
        assert len(serialized["content"]) == 2
        assert serialized["content"][0]["type"] == "text"
        assert serialized["content"][0]["text"] == "Here is the image:"
        assert serialized["content"][1]["type"] == "image_url"

    def test_tool_message_without_parts_backward_compat(self, provider: ZAIProvider):
        """ToolMessage without parts → dict with string content."""
        msg = ToolMessage(
            content="Plain text result",
            tool_call_id="call_1",
            name="read_file",
            parts=None,
        )
        serialized = self._serialize(provider, msg)

        assert serialized["role"] == "tool"
        assert serialized["content"] == "Plain text result"
        assert isinstance(serialized["content"], str)
