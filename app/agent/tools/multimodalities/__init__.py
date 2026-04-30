"""Multimodal generation tools — image, audio, video.

Each submodule ships a single ``Tool`` that is always importable but reads
its provider/model/api-key config from ``{CONFIG_DIR}/multimodal.yaml`` at
call time.  Missing section or missing API-key env var → the tool returns
a clear "not configured" message to the agent instead of raising.
"""

from .image import generate_image
from .video import generate_video

__all__ = ["generate_image", "generate_video"]
