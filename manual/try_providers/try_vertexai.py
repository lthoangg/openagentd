"""Test Vertex AI provider directly — streaming, chat, and tools.

Uses VERTEXAI_API_KEY from .env via settings.
Optionally uses GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION.

Usage:
  uv run python -m manual.try_providers.try_vertexai
  uv run python -m manual.try_providers.try_vertexai --model gemini-3.1-pro-preview
  uv run python -m manual.try_providers.try_vertexai --level high
  uv run python -m manual.try_providers.try_vertexai --tools
  uv run python -m manual.try_providers.try_vertexai --real-tools
  uv run python -m manual.try_providers.try_vertexai --no-stream
  uv run python -m manual.try_providers.try_vertexai --simple
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import settings
from app.agent.providers.vertexai import VertexAIProvider
from manual.try_providers._common import (
    REASONING_PROMPT,
    SIMPLE_PROMPT,
    run_chat,
    run_stream,
)
from manual.try_providers._tools_common import (
    PROMPT_WITH_TOOLS,
    SIMPLE_TEST_TOOLS,
    get_real_tool_defs,
    run_stream_with_tools,
)


async def main():
    p = argparse.ArgumentParser(description="Test Vertex AI provider")
    p.add_argument(
        "--model",
        default="gemini-3.1-pro-preview",
        help="Model (default: gemini-3.1-pro-preview)",
    )
    p.add_argument("--level", default=None, help="Thinking level: low|medium|high")
    p.add_argument("--tools", action="store_true", help="Test with simple tools")
    p.add_argument(
        "--real-tools",
        action="store_true",
        help="Test with actual agent tool schemas (includes memory tools)",
    )
    p.add_argument("--no-stream", action="store_true", help="Non-streaming chat()")
    p.add_argument(
        "--simple", action="store_true", help="Use simple prompt instead of reasoning"
    )
    args = p.parse_args()

    api_key = (
        settings.VERTEXAI_API_KEY.get_secret_value()
        if settings.VERTEXAI_API_KEY
        else None
    )
    if not api_key:
        print("ERROR: VERTEXAI_API_KEY not set in .env")
        return

    model_kwargs: dict = {}
    if args.level:
        model_kwargs["thinking_level"] = args.level

    project = getattr(settings, "GOOGLE_CLOUD_PROJECT", None)
    location = getattr(settings, "GOOGLE_CLOUD_LOCATION", None) or "global"

    provider = VertexAIProvider(
        api_key=api_key,
        model=args.model,
        project=project,
        location=location,
        model_kwargs=model_kwargs,
    )

    prompt = SIMPLE_PROMPT if args.simple else REASONING_PROMPT
    label = "vertexai"
    if project:
        label += f" project={project}"
    if args.level:
        label += f" thinking={args.level}"

    if args.tools or args.real_tools:
        tools = get_real_tool_defs() if args.real_tools else SIMPLE_TEST_TOOLS
        label += " real-tools" if args.real_tools else " simple-tools"
        await run_stream_with_tools(provider, PROMPT_WITH_TOOLS, tools, label=label)
    elif args.no_stream:
        await run_chat(provider, prompt, label=label)
    else:
        await run_stream(provider, prompt, label=label)

    print(f"\n{'=' * 60}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
