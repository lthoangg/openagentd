"""Provider-specific multimodal backends.

## Image backends

Each image backend exposes two async entry points:

- ``generate(cfg, prompt) -> bytes | str`` — text-to-image.
- ``edit(cfg, prompt, images) -> bytes | str`` — image-to-image where
  ``images`` is ``list[tuple[filename, raw_bytes]]``.

``bytes`` = successful image payload; ``str`` = user-facing error message
(prefixed with ``Error:``) that the tool surfaces to the agent.

Image backends are resolved by provider name in ``image.py``. Adding a new
image backend is a two-step change:

1. Add ``backends/<name>.py`` with ``generate`` and ``edit`` coroutines.
2. Register it in ``_IMAGE_BACKENDS`` in ``image.py``.

## Video backends

Each video backend exposes a single async entry point::

    generate(
        cfg, prompt, *,
        image=None,
        last_frame=None,
        reference_images=None,
        overrides=None,
    ) -> bytes | str

All image inputs are ``(filename, raw_bytes)``; sandbox resolution is the
dispatcher's job. Returned ``bytes`` is the mp4 payload. Registered in
``_VIDEO_BACKENDS`` in ``video.py``.
"""

from __future__ import annotations

from app.agent.tools.multimodalities.backends.codex import (
    edit as edit_codex,
)
from app.agent.tools.multimodalities.backends.codex import (
    generate as generate_codex,
)
from app.agent.tools.multimodalities.backends.googlegenai import (
    edit as edit_googlegenai,
)
from app.agent.tools.multimodalities.backends.googlegenai import (
    generate as generate_googlegenai,
)
from app.agent.tools.multimodalities.backends.googlegenai_video import (
    generate as generate_video_googlegenai,
)
from app.agent.tools.multimodalities.backends.openai import (
    edit as edit_openai,
)
from app.agent.tools.multimodalities.backends.openai import (
    generate as generate_openai,
)

__all__ = [
    "edit_codex",
    "edit_googlegenai",
    "edit_openai",
    "generate_codex",
    "generate_googlegenai",
    "generate_openai",
    "generate_video_googlegenai",
]
