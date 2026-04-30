"""Application version — read once from version.txt at import time."""

from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "version.txt"
VERSION: str = (
    _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"
)
