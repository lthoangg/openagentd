"""Test DeepSeek provider directly — streaming, chat, and tools.

Uses DEEPSEEK_API_KEY from .env via settings.

Usage:
  uv run python -m manual.try_providers.try_deepseek
  uv run python -m manual.try_providers.try_deepseek --model deepseek-v4-pro
  uv run python -m manual.try_providers.try_deepseek --tools
  uv run python -m manual.try_providers.try_deepseek --real-tools
  uv run python -m manual.try_providers.try_deepseek --no-stream
  uv run python -m manual.try_providers.try_deepseek --simple
"""

from __future__ import annotations

import argparse
import asyncio

from app.agent.providers.deepseek import DeepSeekProvider
from app.core.config import settings
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
    p = argparse.ArgumentParser(description="Test DeepSeek provider")
    p.add_argument(
        "--model",
        default="deepseek-v4-flash",
        help="Model (default: deepseek-v4-flash)",
    )
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
        settings.DEEPSEEK_API_KEY.get_secret_value()
        if settings.DEEPSEEK_API_KEY
        else None
    )
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set in .env")
        return

    provider = DeepSeekProvider(api_key=api_key, model=args.model)

    prompt = SIMPLE_PROMPT if args.simple else REASONING_PROMPT
    label = f"deepseek model={args.model}"

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
