"""Manual E2E smoketest for the OpenAI image edit backend.

Usage:
    uv run python manual/image_edit_smoketest.py

Requires ``OPENAI_API_KEY`` in the environment (or ``.env``).

Flow:
1. Call the ``generate`` backend to create two small source PNGs.
2. Call the ``edit`` backend with those PNGs + a compose prompt.
3. Write all outputs to ``/tmp/image_edit_smoke/`` for eyeballing.

No sandbox, no agent loop — directly exercises the backend HTTP path.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from app.agent.tools.multimodalities._config import MediaSectionConfig
from app.agent.tools.multimodalities.backends.openai import edit, generate

OUT = Path("/tmp/image_edit_smoke")
CFG = MediaSectionConfig(
    provider="openai",
    model="gpt-image-2",
    extras={"size": "1024x1024", "quality": "low"},  # low = fastest/cheapest
)


async def _make_source(prompt: str, name: str) -> Path:
    print(f"→ generating {name}: {prompt!r}")
    result = await generate(CFG, prompt)
    if isinstance(result, str):
        sys.exit(f"generate failed: {result}")
    path = OUT / name
    path.write_bytes(result)
    print(f"  wrote {path} ({len(result):,} bytes)")
    return path


async def _edit_sources(sources: list[Path], prompt: str, name: str) -> Path:
    print(f"→ editing {[p.name for p in sources]} with prompt: {prompt!r}")
    blobs = [(p.name, p.read_bytes()) for p in sources]
    result = await edit(CFG, prompt, blobs)
    if isinstance(result, str):
        sys.exit(f"edit failed: {result}")
    path = OUT / name
    path.write_bytes(result)
    print(f"  wrote {path} ({len(result):,} bytes)")
    return path


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    red = await _make_source("a solid red cube on a white background", "red-cube.png")
    blue = await _make_source(
        "a solid blue sphere on a white background", "blue-sphere.png"
    )
    await _edit_sources(
        [red, blue],
        "place the red cube and the blue sphere side by side on a wooden desk, "
        "photorealistic, soft studio lighting",
        "composed.png",
    )
    print(f"\nDone. Open {OUT} to inspect the PNGs.")


if __name__ == "__main__":
    asyncio.run(main())
