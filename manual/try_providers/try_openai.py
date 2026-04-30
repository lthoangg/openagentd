"""Test OpenAI provider directly — both completions and responses endpoints.

Uses OPENAI_API_KEY from .env via settings.

Usage:
  uv run python -m manual.try_providers.try_openai
  uv run python -m manual.try_providers.try_openai --model gpt-5.4-mini --level low
  uv run python -m manual.try_providers.try_openai --model gpt-5.4-mini --responses
  uv run python -m manual.try_providers.try_openai --no-stream
"""

import argparse
import asyncio

from app.core.config import settings
from app.agent.providers.openai import OpenAIProvider
from manual.try_providers._common import (
    REASONING_PROMPT,
    SIMPLE_PROMPT,
    run_chat,
    run_stream,
)


async def main():
    p = argparse.ArgumentParser(description="Test OpenAI provider")
    p.add_argument(
        "--model", default="gpt-5.4-mini", help="Model (default: gpt-5.4-mini)"
    )
    p.add_argument("--level", default=None, help="Thinking level: low|medium|high")
    p.add_argument("--responses", action="store_true", help="Use /responses endpoint")
    p.add_argument("--no-stream", action="store_true", help="Non-streaming chat()")
    p.add_argument(
        "--simple", action="store_true", help="Use simple prompt instead of reasoning"
    )
    args = p.parse_args()

    api_key = (
        settings.OPENAI_API_KEY.get_secret_value() if settings.OPENAI_API_KEY else None
    )
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in .env")
        return

    model_kwargs: dict = {}
    if args.level:
        model_kwargs["thinking_level"] = args.level
    if args.responses:
        model_kwargs["responses_api"] = True

    provider = OpenAIProvider(
        api_key=api_key,
        model=args.model,
        model_kwargs=model_kwargs,
    )

    prompt = SIMPLE_PROMPT if args.simple else REASONING_PROMPT
    label = "responses" if args.responses else "completions"
    if args.level:
        label += f" thinking={args.level}"

    if args.no_stream:
        await run_chat(provider, prompt, label=label)
    else:
        await run_stream(provider, prompt, label=label)

    print(f"\n{'=' * 60}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
