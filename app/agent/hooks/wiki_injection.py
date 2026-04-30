"""WikiInjectionHook — inject wiki/USER.md into the system prompt.

Every LLM call receives ``wiki/USER.md`` in full (always — identity + preferences).
Topic injection is no longer automatic; the agent uses the ``wiki_search`` tool
to look up topics explicitly.

BM25 scoring helpers (_score_topics, _tokenize, etc.) are kept here because
the ``wiki_search`` tool imports them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from app.agent.hooks.base import BaseAgentHook

if TYPE_CHECKING:
    from app.agent.schemas.chat import AssistantMessage
    from app.agent.state import (
        AgentState,
        ModelCallHandler,
        ModelRequest,
        RunContext,
    )

# ── Tuning constants (kept for wiki_search tool) ─────────────────────────────

#: Common one-word stopwords excluded from the trivial token count.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "hi",
        "hey",
        "hello",
        "ok",
        "okay",
        "yes",
        "no",
        "yep",
        "nope",
        "sure",
        "thanks",
        "thank",
        "thx",
        "ty",
        "np",
        "please",
        "plz",
        "got",
        "noted",
        "ack",
        "good",
        "great",
        "nice",
        "cool",
        "fine",
        "bye",
        "cya",
        "later",
        "hmm",
        "hm",
        "uh",
        "um",
        "ah",
        "oh",
    }
)

#: Minimum meaningful tokens for a query to be considered non-trivial.
_TRIVIAL_MIN_TOKENS = 3

# ── Hook ─────────────────────────────────────────────────────────────────────


class WikiInjectionHook(BaseAgentHook):
    """Inject wiki/USER.md into the system prompt on every LLM call."""

    async def wrap_model_call(
        self,
        ctx: "RunContext",
        state: "AgentState",
        request: "ModelRequest",
        handler: "ModelCallHandler",
    ) -> "AssistantMessage":
        user_block = self._read_user_md()
        if not user_block:
            return await handler(request)
        header = "## About the user\n\n"
        block = header + user_block
        new_prompt = (
            f"{request.system_prompt}\n\n{block}" if request.system_prompt else block
        )
        return await handler(request.override(system_prompt=new_prompt))

    def _read_user_md(self) -> str:
        from app.services.wiki import USER_FILE, wiki_root

        root = wiki_root()
        user_path = root / USER_FILE
        if not user_path.exists():
            return ""
        try:
            return user_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return ""


# ── BM25-style relevance scoring (used by wiki_search tool) ──────────────────


def _is_trivial_query(query: str) -> bool:
    """Return True when *query* has too few meaningful tokens to warrant BM25 scoring."""
    tokens = _tokenize(query)
    meaningful = [t for t in tokens if t not in _STOPWORDS]
    return len(meaningful) < _TRIVIAL_MIN_TOKENS


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, drop tokens shorter than 2 chars."""
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) >= 2]


def _score_topics(query: str, topics: list) -> list[tuple]:
    """Score each topic against *query* using weighted token overlap.

    Returns topics sorted descending by score.  Topics with zero overlap are
    included (score=0) so the caller can still render a complete index.
    """
    if not query.strip():
        return [(t, 0.0) for t in topics]

    query_tokens = set(_tokenize(query))
    results: list[tuple] = []

    for info in topics:
        stem = Path(info.path).stem  # e.g. "auth-strategy"
        desc_tokens = _tokenize(info.description)
        tag_tokens = [t for tag in info.tags for t in _tokenize(tag)]
        stem_tokens = _tokenize(stem)

        score = 0.0
        for tok in desc_tokens:
            if tok in query_tokens:
                score += 1.0
        for tok in tag_tokens:
            if tok in query_tokens:
                score += 1.5
        for tok in stem_tokens:
            if tok in query_tokens:
                score += 0.5

        results.append((info, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def _extract_query(request: "ModelRequest") -> str:
    """Return the last user message content from the request, or empty string."""
    from app.agent.schemas.chat import HumanMessage

    for msg in reversed(request.messages):
        if isinstance(msg, HumanMessage) and msg.content:
            return (msg.content or "")[:500]
    return ""


# Module-level instance for convenience.
default_wiki_injection_hook = WikiInjectionHook()


__all__ = [
    "WikiInjectionHook",
    "default_wiki_injection_hook",
    "_is_trivial_query",
    "_score_topics",
    "_tokenize",
    "_extract_query",
]
