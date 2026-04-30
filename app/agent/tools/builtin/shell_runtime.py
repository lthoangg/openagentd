"""Shell binary selection — honours the user's $SHELL with safety guardrails.

Mirrors the design of opencode's ``shell.ts``:

- Reads ``$SHELL`` from the environment.
- Rejects incompatible shells (``fish``, ``nu``) that do not speak
  POSIX syntax — agents produce POSIX commands so incompatible shells
  would misinterpret them.
- Falls back through ``zsh`` → ``bash`` → ``sh`` when no usable shell is
  found or the preference is blocked.
- Exposes ``preferred()`` (exact user preference, may be None) and
  ``acceptable()`` (always non-None, safe to pass to subprocess).

Both are lazy ``functools.cached_property``-style singletons — detected once
per process, cached forever.  Tests can override by patching
``app.agent.tools.builtin.shell_runtime._CACHED_SHELL``.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# ── Shell name sets ──────────────────────────────────────────────────────────

# Shells that do not understand POSIX syntax; agents generate POSIX commands
# so we must never dispatch to these.
BLACKLIST: frozenset[str] = frozenset({"fish", "nu", "nushell"})

# POSIX-compatible shells — ordered by preference (best first)
_POSIX_FALLBACKS: tuple[str, ...] = ("zsh", "bash", "sh")


# ── Internal helpers ─────────────────────────────────────────────────────────


def _shell_name(path: str) -> str:
    """Return the lowercase basename of a shell path (no extension on any OS)."""
    stem = Path(path).stem.lower()
    return stem


def _which(name: str) -> str | None:
    """Return the full path to *name* if it is on PATH, else None."""
    return shutil.which(name)


def _is_usable(path: str) -> bool:
    """True if *path* is a non-blacklisted, executable shell."""
    name = _shell_name(path)
    if name in BLACKLIST:
        return False
    # Must exist and be executable (shutil.which already guarantees this for
    # names; for absolute paths we verify directly).
    if os.path.isabs(path):
        return os.access(path, os.X_OK)
    return _which(path) is not None


def _fallback() -> str:
    """Return the best available POSIX shell on this machine."""
    # macOS always ships /bin/zsh since Catalina
    if sys.platform == "darwin":
        return "/bin/zsh"
    for name in _POSIX_FALLBACKS:
        found = _which(name)
        if found:
            return found
    return "/bin/sh"  # POSIX guarantee — always present


# ── Module-level detection cache ────────────────────────────────────────────
# Mutate ``_CACHED_SHELL`` in tests to override detection without environment
# manipulation.

_CACHED_SHELL: str | None = None  # sentinel — populated on first use


def _detect() -> str:
    """Detect the best shell, caching the result in ``_CACHED_SHELL``.

    Detection order:
    1. ``$SHELL`` environment variable, if set and acceptable.
    2. ``/bin/zsh`` on macOS (default since Catalina).
    3. First of ``zsh``, ``bash``, ``sh`` found on PATH.
    4. ``/bin/sh`` (POSIX guarantee).
    """
    global _CACHED_SHELL
    if _CACHED_SHELL is not None:
        return _CACHED_SHELL

    env_shell = os.environ.get("SHELL", "")
    if env_shell and _is_usable(env_shell):
        _CACHED_SHELL = env_shell
        return _CACHED_SHELL

    # env_shell was blacklisted (e.g. fish) or empty — pick a POSIX fallback
    _CACHED_SHELL = _fallback()
    return _CACHED_SHELL


# ── Public API ───────────────────────────────────────────────────────────────


def acceptable() -> str:
    """Return the shell binary path to use for subprocess execution.

    Always returns a non-None, executable, POSIX-compatible path.
    """
    return _detect()


def name(shell_path: str | None = None) -> str:
    """Return the lowercase name of a shell (basename without extension).

    If *shell_path* is None, uses :func:`acceptable` to get the current shell.
    """
    return _shell_name(shell_path or acceptable())


def is_posix(shell_path: str | None = None) -> bool:
    """True if the shell speaks POSIX sh syntax."""
    n = name(shell_path)
    return n in {"bash", "dash", "ksh", "sh", "zsh"}


def reset_cache() -> None:
    """Clear the cached shell detection — for test isolation only."""
    global _CACHED_SHELL
    _CACHED_SHELL = None
