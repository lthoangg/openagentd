"""OpenAI Responses API handler (/v1/responses).

Used automatically when thinking_level is set, or explicitly via
``responses_api: true`` in model_kwargs. Supports reasoning models
(e.g. gpt-5.4) with tool use.

Key differences from Chat Completions:
- Does not support temperature / top_p
- Uses a different input/output format
- Tool call IDs use item_id (prefix: fc_)
- Function names arrive via response.output_item.added events
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, AsyncIterator

import httpx
from loguru import logger

from app.agent.schemas.chat import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionDelta,
    ChatMessage,
    FunctionCall,
    FunctionCallDelta,
    HumanMessage,
    ImageDataBlock,
    ImageUrlBlock,
    SystemMessage,
    TextBlock,
    ToolCall,
    ToolCallDelta,
    ToolMessage,
    Usage,
)

if TYPE_CHECKING:
    pass


class ResponsesHandler:
    """Handles all interaction with /v1/responses."""

    def __init__(self, model: str, base_url: str, headers: dict[str, str]) -> None:
        self.model = model
        self.base_url = base_url
        self.headers = headers

    # ------------------------------------------------------------------
    # Message / tool conversion
    # ------------------------------------------------------------------

    def convert_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert canonical messages to Responses API input format."""
        input_items: list[dict[str, Any]] = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                input_items.append({"role": "system", "content": msg.content})

            elif isinstance(msg, HumanMessage):
                if msg.parts:
                    resp_parts: list[dict] = []
                    for part in msg.parts:
                        if isinstance(part, TextBlock):
                            resp_parts.append({"type": "input_text", "text": part.text})
                        elif isinstance(part, ImageUrlBlock):
                            resp_parts.append(
                                {
                                    "type": "input_image",
                                    "image_url": part.url,
                                    "detail": part.detail or "auto",
                                }
                            )
                        elif isinstance(part, ImageDataBlock):
                            resp_parts.append(
                                {
                                    "type": "input_image",
                                    "image_url": f"data:{part.media_type};base64,{part.data}",
                                    "detail": "auto",
                                }
                            )
                    input_items.append({"role": "user", "content": resp_parts})
                else:
                    input_items.append({"role": "user", "content": msg.content})

            elif isinstance(msg, AssistantMessage):
                if msg.content:
                    input_items.append({"role": "assistant", "content": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        # Only include if call_id is non-empty
                        if tc.id:
                            input_items.append(
                                {
                                    "type": "function_call",
                                    "call_id": tc.id,
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                    if isinstance(tc.function.arguments, str)
                                    else "{}",
                                }
                            )

            elif isinstance(msg, ToolMessage):
                # Only include if call_id is non-empty
                if msg.tool_call_id:
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": msg.tool_call_id,
                            "output": msg.content or "",
                        }
                    )

        return input_items

    def convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Convert canonical tools to Responses API format (flat, not wrapped)."""
        if not tools:
            return []
        result = []
        for t in tools:
            if t.get("type") == "function":
                f = t["function"]
                result.append(
                    {
                        "type": "function",
                        "name": f["name"],
                        "description": f.get("description", ""),
                        "parameters": f.get("parameters", {}),
                    }
                )
        return result

    # ------------------------------------------------------------------
    # Request builder
    # ------------------------------------------------------------------

    def build_request(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        merged: dict[str, Any],
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "input": self.convert_messages(messages),
            "stream": stream,
        }

        resp_tools = self.convert_tools(tools)
        if resp_tools:
            body["tools"] = resp_tools

        # Responses API does not support temperature / top_p
        if merged.get("max_tokens") is not None:
            body["max_output_tokens"] = merged["max_tokens"]

        self.customize_thinking(merged, body)
        return body

    def customize_thinking(self, merged: dict[str, Any], body: dict[str, Any]) -> None:
        """Apply provider-specific reasoning translation for the Responses API.

        Default behaviour: map ``thinking_level`` to ``reasoning: {effort, summary}``.
        Subclasses override to gate by model or use a different shape.

        Mutates ``body`` in place.
        """
        thinking_level = merged.get("thinking_level")
        if thinking_level and thinking_level not in ("none", "off"):
            body["reasoning"] = {"effort": thinking_level, "summary": "auto"}

    def _extract_call_id_and_name(self, event: dict[str, Any]) -> tuple[str, str]:
        """Pull the tool-call ID and (optional) function name from a streaming event.

        Default behaviour follows the canonical OpenAI Responses wire format:
        ``item_id`` carries the stable tool-call ID (prefix ``fc_``) and the
        function ``name`` is *only* delivered via ``response.output_item.added``
        events — never inline on ``function_call_arguments.delta`` / ``done``.

        Subclasses override this hook when their gateway diverges from the
        canonical shape (e.g. GitHub Copilot uses ``call_id`` and embeds
        ``name`` directly on argument-stream events).
        """
        return event.get("item_id", ""), ""

    # ------------------------------------------------------------------
    # Response parsing — non-streaming
    # ------------------------------------------------------------------

    def parse_response(self, data: dict) -> AssistantMessage:
        output = data.get("output", [])
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for item in output:
            item_type = item.get("type", "")
            if item_type == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        content_parts.append(part.get("text", ""))
            elif item_type == "reasoning":
                for s in item.get("summary", []):
                    if s.get("type") == "summary_text":
                        reasoning_parts.append(s.get("text", ""))
            elif item_type == "function_call":
                tool_calls.append(
                    ToolCall(
                        id=item.get("call_id", item.get("id", "")),
                        function=FunctionCall(
                            name=item.get("name", ""),
                            arguments=item.get("arguments", "{}"),
                        ),
                    )
                )

        return AssistantMessage(
            content="\n".join(content_parts) if content_parts else None,
            reasoning_content="\n".join(reasoning_parts) if reasoning_parts else None,
            tool_calls=tool_calls if tool_calls else None,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        merged: dict[str, Any],
    ) -> AssistantMessage:
        body = self.build_request(messages, tools, stream=False, merged=merged)
        url = f"{self.base_url}/responses"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, headers=self.headers, json=body, timeout=120.0
            )
            if response.status_code >= 400:
                logger.error(
                    "openai_chat_error status={} body={}",
                    response.status_code,
                    response.text[:500],
                )
            response.raise_for_status()
            return self.parse_response(response.json())

    async def stream(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        merged: dict[str, Any],
    ) -> AsyncIterator[ChatCompletionChunk]:
        body = self.build_request(messages, tools, stream=True, merged=merged)
        url = f"{self.base_url}/responses"

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, headers=self.headers, json=body, timeout=120.0
            ) as response:
                if response.status_code >= 400:
                    err_body = await response.aread()
                    logger.error(
                        "openai_stream_error status={} body={}",
                        response.status_code,
                        err_body[:500],
                    )
                    response.raise_for_status()

                async for chunk in self._parse_stream(response):
                    yield chunk

    # ------------------------------------------------------------------
    # Streaming parser
    # ------------------------------------------------------------------

    async def _parse_stream(self, response: Any) -> AsyncIterator[ChatCompletionChunk]:
        """Parse SSE stream from /responses API into ChatCompletionChunk objects."""
        response_id = ""
        current_tool_call_index = -1
        tool_call_map: dict[str, int] = {}  # item_id -> index
        tool_names: dict[str, str] = {}  # item_id -> function_name

        async for line in response.aiter_lines():
            line = line.strip()
            if line.startswith("event: "):
                continue
            if not line.startswith("data: "):
                continue

            data_str = line[6:]
            if data_str == "[DONE]":
                break

            try:
                event = json.loads(data_str)
            except (json.JSONDecodeError, ValueError):
                continue

            etype = event.get("type", "")

            if etype == "response.created":
                response_id = event.get("response", {}).get("id", "")

            elif etype == "response.output_item.added":
                # Capture function name from the item header event
                item = event.get("item", {})
                item_id = item.get("id", "")
                if item.get("type") == "function_call" and item_id:
                    fn_name = item.get("name", "")
                    if fn_name:
                        tool_names[item_id] = fn_name

            elif etype == "response.reasoning_summary_text.delta":
                delta_text = event.get("delta", "")
                if delta_text:
                    yield ChatCompletionChunk(
                        id=response_id,
                        created=int(time.time()),
                        model=self.model,
                        choices=[
                            ChatCompletionChunkChoice(
                                index=0,
                                delta=ChatCompletionDelta(reasoning_content=delta_text),
                                finish_reason=None,
                            )
                        ],
                    )

            elif etype == "response.output_text.delta":
                delta_text = event.get("delta", "")
                if delta_text:
                    yield ChatCompletionChunk(
                        id=response_id,
                        created=int(time.time()),
                        model=self.model,
                        choices=[
                            ChatCompletionChunkChoice(
                                index=0,
                                delta=ChatCompletionDelta(content=delta_text),
                                finish_reason=None,
                            )
                        ],
                    )

            elif etype == "response.function_call_arguments.delta":
                # item_id is the stable tool call ID (prefix: fc_)
                call_id, inline_name = self._extract_call_id_and_name(event)
                args_delta = event.get("delta", "")

                first_delta = call_id not in tool_call_map
                if first_delta:
                    current_tool_call_index += 1
                    tool_call_map[call_id] = current_tool_call_index
                if inline_name and call_id and call_id not in tool_names:
                    tool_names[call_id] = inline_name

                idx = tool_call_map[call_id]
                emit_name = inline_name if first_delta and inline_name else None

                yield ChatCompletionChunk(
                    id=response_id,
                    created=int(time.time()),
                    model=self.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=ChatCompletionDelta(
                                tool_calls=[
                                    ToolCallDelta(
                                        index=idx,
                                        id=call_id or None,
                                        function=FunctionCallDelta(
                                            name=emit_name or None,
                                            arguments=args_delta,
                                        ),
                                    )
                                ]
                            ),
                            finish_reason=None,
                        )
                    ],
                )

            elif etype == "response.function_call_arguments.done":
                call_id, inline_name = self._extract_call_id_and_name(event)
                fn_name = inline_name or tool_names.get(call_id, "")
                fn_args = event.get("arguments", "{}")

                if call_id not in tool_call_map:
                    current_tool_call_index += 1
                    tool_call_map[call_id] = current_tool_call_index
                if fn_name and call_id and call_id not in tool_names:
                    tool_names[call_id] = fn_name

                idx = tool_call_map[call_id]

                yield ChatCompletionChunk(
                    id=response_id,
                    created=int(time.time()),
                    model=self.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=ChatCompletionDelta(
                                tool_calls=[
                                    ToolCallDelta(
                                        index=idx,
                                        id=call_id,
                                        function=FunctionCallDelta(
                                            name=fn_name,
                                            arguments=fn_args,
                                        ),
                                    )
                                ]
                            ),
                            finish_reason=None,
                        )
                    ],
                )

            elif etype == "response.output_text.done":
                yield ChatCompletionChunk(
                    id=response_id,
                    created=int(time.time()),
                    model=self.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=ChatCompletionDelta(),
                            finish_reason="stop",
                        )
                    ],
                )

            elif etype == "response.completed":
                usage_data = event.get("response", {}).get("usage", {})
                if usage_data:
                    input_details = usage_data.get("input_tokens_details", {})
                    output_details = usage_data.get("output_tokens_details", {})
                    yield ChatCompletionChunk(
                        id=response_id,
                        created=int(time.time()),
                        model=self.model,
                        choices=[],
                        usage=Usage(
                            prompt_tokens=usage_data.get("input_tokens", 0),
                            completion_tokens=usage_data.get("output_tokens", 0),
                            total_tokens=usage_data.get("total_tokens", 0),
                            cached_tokens=input_details.get("cached_tokens") or None,
                            thoughts_tokens=output_details.get("reasoning_tokens")
                            or None,
                        ),
                    )
