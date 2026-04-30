"""Shared multimodal attachment hydration utilities.

Builds LLM content parts (TextBlock / ImageDataBlock) from attachment
metadata dicts stored in ``SessionMessage.extra.attachments``.

Used by:
- ``app.api.routes.chat`` — at message send time (current turn)
- ``app.services.chat_service`` — at history load time (cross-turn re-hydration)

The output is consumed only by the LLM dispatch path; the frontend never
renders it (it renders ``extra.attachments`` directly).  This means
diagnostic/path-hint TextBlocks added here are model-only by construction
— no UI suppression rule is needed.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

from loguru import logger

from app.agent.schemas.chat import ImageDataBlock, TextBlock


def build_parts_from_metas(
    message: str,
    attachment_metas: list[dict],
) -> list:
    """Build LLM content parts from attachment metadata.

    Strategy per attachment:

    - ``converted_text`` present → fast path: use cached string as TextBlock.
      No disk I/O. Used for text files and successfully markitdown-converted docs.
    - ``category == "image"`` or native-PDF doc without ``converted_text`` →
      slow path: read raw bytes from ``att["path"]``, base64-encode → ImageDataBlock.

    Image attachments are preceded by a ``[Attached image saved at
    uploads/<filename>]`` TextBlock so the model knows the workspace-relative
    path it can pass to workspace-bound tools (``generate_image`` /
    ``generate_video`` / shell). Without this hint the model only sees pixels
    and tends to hallucinate paths like ``/mnt/data/0.png``.

    Content blocks come first, user message text last (context → question order).

    Args:
        message: The user's typed message text.
        attachment_metas: List of attachment dicts from ``extra.attachments``.

    Returns:
        List of TextBlock / ImageDataBlock objects, always ending with a
        TextBlock for ``message``.  Empty list is not returned — at minimum
        the trailing TextBlock for ``message`` is included.
    """
    parts: list = []

    for att in attachment_metas:
        category = att.get("category", "image")
        original_name = att.get("original_name", att.get("filename", "file"))

        if "converted_text" in att:
            # Me fast path — cached content, no disk read
            label = "[File" if category == "text" else "[Document"
            parts.append(
                TextBlock(text=f"{label}: {original_name}]\n{att['converted_text']}")
            )

        elif category in ("image", "document"):
            # Me slow path — read from disk via the persisted absolute path
            raw_path = att.get("path")
            if not raw_path:
                logger.warning(
                    "attachment_path_missing original_name={}", original_name
                )
                parts.append(TextBlock(text=f"[File not found: {original_name}]"))
                continue
            path = Path(raw_path)
            # Time the disk-read + base64-encode step. Rehydration runs on
            # every history load and current-turn dispatch, so this is the
            # signal we need to spot a slow file or a base64 bottleneck.
            start = time.perf_counter()
            try:
                raw = path.read_bytes()
            except OSError:
                logger.warning("attachment_file_missing path={}", path)
                parts.append(TextBlock(text=f"[File not found: {original_name}]"))
                continue
            # Path hint precedes the pixels so the model binds image →
            # ``uploads/<filename>`` before it reaches for tool calls.
            # Image-only by design — text/document use the fast path above
            # and inline their content directly.
            if category == "image":
                stored_filename = att.get("filename")
                if stored_filename:
                    parts.append(
                        TextBlock(
                            text=f"[Attached image saved at uploads/{stored_filename}]"
                        )
                    )
            b64 = base64.b64encode(raw).decode("ascii")
            parts.append(
                ImageDataBlock(data=b64, media_type=att.get("media_type", "image/jpeg"))
            )
            duration_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "attachment_rehydrated category={} bytes={} duration_ms={:.1f} path={}",
                category,
                len(raw),
                duration_ms,
                path,
            )

    # Me user text always last — natural order: context → question
    parts.append(TextBlock(text=message))
    return parts
