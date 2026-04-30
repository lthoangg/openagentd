"""Test GeminiCLI provider directly — streaming, chat, and tools.

No API key needed — uses OAuth credentials from ~/.gemini/oauth_creds.json
(written by the `gemini` CLI tool). Run `gemini` once to authenticate.

Usage:
  uv run python -m manual.try_providers.try_geminicli
  uv run python -m manual.try_providers.try_geminicli --model gemini-3.1-pro
  uv run python -m manual.try_providers.try_geminicli --level high
  uv run python -m manual.try_providers.try_geminicli --tools
  uv run python -m manual.try_providers.try_geminicli --real-tools
  uv run python -m manual.try_providers.try_geminicli --no-stream
  uv run python -m manual.try_providers.try_geminicli --simple
"""

from __future__ import annotations

import argparse
import asyncio

from app.agent.providers.geminicli import GeminiCLIProvider
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
    p = argparse.ArgumentParser(description="Test GeminiCLI provider")
    p.add_argument(
        "--model",
        default="gemini-3.1-pro",
        help="Model (default: gemini-3.1-pro)",
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

    model_kwargs: dict = {}
    if args.level:
        model_kwargs["thinking_level"] = args.level

    try:
        provider = GeminiCLIProvider(
            model=args.model,
            model_kwargs=model_kwargs,
        )
    except Exception as e:
        print(f"ERROR: Could not initialize GeminiCLI provider: {e}")
        print(
            "Hint: Run `gemini` CLI once to authenticate (creates ~/.gemini/oauth_creds.json)"
        )
        return

    prompt = SIMPLE_PROMPT if args.simple else REASONING_PROMPT
    label = "geminicli"
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
