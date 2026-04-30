"""Test Copilot provider directly — both completions and responses endpoints.

Requires GitHub OAuth token (run: uv run openagentd auth copilot).

Usage:
  uv run python -m manual.try_providers.try_copilot
  uv run python -m manual.try_providers.try_copilot --model gpt-5.4-mini --level low
  uv run python -m manual.try_providers.try_copilot --model gpt-5-mini --level medium
  uv run python -m manual.try_providers.try_copilot --no-stream
"""

import argparse
import asyncio

from app.agent.providers.copilot import CopilotProvider
from manual.try_providers._common import (
    REASONING_PROMPT,
    SIMPLE_PROMPT,
    run_chat,
    run_stream,
)


async def main():
    p = argparse.ArgumentParser(description="Test Copilot provider")
    p.add_argument("--model", default="gpt-5-mini", help="Model (default: gpt-5-mini)")
    p.add_argument("--level", default=None, help="Thinking level: low|medium|high")
    p.add_argument("--no-stream", action="store_true", help="Non-streaming chat()")
    p.add_argument(
        "--simple", action="store_true", help="Use simple prompt instead of reasoning"
    )
    args = p.parse_args()

    model_kwargs: dict = {}
    if args.level:
        model_kwargs["thinking_level"] = args.level

    provider = CopilotProvider(
        model=args.model,
        model_kwargs=model_kwargs,
    )

    prompt = SIMPLE_PROMPT if args.simple else REASONING_PROMPT
    label = provider._endpoint_type
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
