"""Lazy OTel instruments for multimodalities tools.

Histograms are created on first access via ``get_meter()``. Using module-level
lazy singletons keeps instrument construction out of import-time — the OTel
SDK may not be initialised when ``image.py`` is first imported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.otel import get_meter

if TYPE_CHECKING:
    from opentelemetry.metrics import Histogram


_image_duration: "Histogram | None" = None
_image_output_bytes: "Histogram | None" = None
_video_duration: "Histogram | None" = None
_video_output_bytes: "Histogram | None" = None


def image_duration_histogram() -> "Histogram":
    """Duration of a full ``generate_image`` tool call, in seconds."""
    global _image_duration
    if _image_duration is None:
        _image_duration = get_meter().create_histogram(
            name="openagentd.image.generation.duration",
            description="generate_image tool duration (includes backend HTTP + disk write)",
            unit="s",
        )
    return _image_duration


def image_output_bytes_histogram() -> "Histogram":
    """Size of the image written to the workspace on success, in bytes."""
    global _image_output_bytes
    if _image_output_bytes is None:
        _image_output_bytes = get_meter().create_histogram(
            name="openagentd.image.output.bytes",
            description="generate_image output file size (success only)",
            unit="By",
        )
    return _image_output_bytes


def video_duration_histogram() -> "Histogram":
    """Duration of a full ``generate_video`` tool call, in seconds.

    Video generation is long-running (11s–6min per Veo docs) so this
    histogram's buckets sit in a very different range from the image one —
    give dashboards a separate instrument instead of overloading the image
    histogram with a noisy tail.
    """
    global _video_duration
    if _video_duration is None:
        _video_duration = get_meter().create_histogram(
            name="openagentd.video.generation.duration",
            description="generate_video tool duration (predictLongRunning + poll + download)",
            unit="s",
        )
    return _video_duration


def video_output_bytes_histogram() -> "Histogram":
    """Size of the video mp4 written to the workspace on success, in bytes."""
    global _video_output_bytes
    if _video_output_bytes is None:
        _video_output_bytes = get_meter().create_histogram(
            name="openagentd.video.output.bytes",
            description="generate_video output file size (success only)",
            unit="By",
        )
    return _video_output_bytes
