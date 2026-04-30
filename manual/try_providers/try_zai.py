"""Test ZAI provider directly — streaming, chat, and tools.

Uses ZAI_API_KEY from .env via settings.

Usage:
  uv run python -m manual.try_providers.try_zai
  uv run python -m manual.try_providers.try_zai --model deepseek-chat
  uv run python -m manual.try_providers.try_zai --level high
  uv run python -m manual.try_providers.try_zai --tools
  uv run python -m manual.try_providers.try_zai --real-tools
  uv run python -m manual.try_providers.try_zai --no-stream
  uv run python -m manual.try_providers.try_zai --simple
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import settings
from app.agent.providers.zai import ZAIProvider
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
    p = argparse.ArgumentParser(description="Test ZAI provider")
    p.add_argument(
        "--model",
        default="deepseek-chat",
        help="Model (default: deepseek-chat)",
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

    api_key = settings.ZAI_API_KEY.get_secret_value() if settings.ZAI_API_KEY else None
    if not api_key:
        print("ERROR: ZAI_API_KEY not set in .env")
        return

    model_kwargs: dict = {}
    if args.level:
        model_kwargs["thinking_level"] = args.level

    provider = ZAIProvider(
        api_key=api_key,
        model=args.model,
        model_kwargs=model_kwargs,
    )

    prompt = SIMPLE_PROMPT if args.simple else REASONING_PROMPT
    label = "zai"
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
