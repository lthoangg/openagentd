"""Tests for WikiInjectionHook — USER.md injection only.

Topic injection is no longer automatic; the agent uses wiki_search explicitly.
BM25 scoring helpers are still tested here since wiki_search imports them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.hooks.wiki_injection import (
    WikiInjectionHook,
    _score_topics,
    _tokenize,
)
from app.agent.schemas.chat import AssistantMessage, HumanMessage
from app.agent.state import AgentState, ModelRequest, RunContext
from app.services.wiki import WikiFileInfo


@pytest.fixture(autouse=True)
def _wiki_dir(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    target = tmp_path / "wiki"
    monkeypatch.setattr(settings, "OPENAGENTD_WIKI_DIR", str(target))
    target.mkdir(parents=True, exist_ok=True)
    yield target


def _ctx() -> RunContext:
    return RunContext(session_id="s1", run_id="r1", agent_name="bot")


def _state() -> AgentState:
    return AgentState(
        messages=[HumanMessage(content="hi")],
        system_prompt="Base prompt.",
    )


def _request(prompt: str = "Base prompt.", last_user: str = "hi") -> ModelRequest:
    return ModelRequest(
        messages=(HumanMessage(content=last_user),),
        system_prompt=prompt,
    )


async def _invoke(hook: WikiInjectionHook, req: ModelRequest) -> str:
    received: list[str] = []

    async def handler(r: ModelRequest) -> AssistantMessage:
        received.append(r.system_prompt)
        return AssistantMessage(content="ok")

    await hook.wrap_model_call(_ctx(), _state(), req, handler)
    return received[0]


# ── USER.md injection ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_user_md_passes_through_unchanged(_wiki_dir: Path):
    """When USER.md doesn't exist, the prompt is passed through unchanged."""
    hook = WikiInjectionHook()
    req = _request("Base prompt.")
    received: list[str] = []

    async def handler(r: ModelRequest) -> AssistantMessage:
        received.append(r.system_prompt)
        return AssistantMessage(content="ok")

    await hook.wrap_model_call(_ctx(), _state(), req, handler)
    assert received[0] == "Base prompt."


@pytest.mark.asyncio
async def test_user_md_injected_in_full(_wiki_dir: Path):
    """USER.md content should be injected into the system prompt."""
    (_wiki_dir / "USER.md").write_text(
        "# User\n\n## Identity\nHoang, Saigon.\n", encoding="utf-8"
    )
    hook = WikiInjectionHook()
    result = await _invoke(hook, _request("Base."))
    assert "Hoang, Saigon." in result
    assert "## About the user" in result


@pytest.mark.asyncio
async def test_existing_prompt_preserved(_wiki_dir: Path):
    """The original system prompt should be preserved before the injected block."""
    (_wiki_dir / "USER.md").write_text("# User\n", encoding="utf-8")
    hook = WikiInjectionHook()
    result = await _invoke(hook, _request("CUSTOM BASE"))
    assert result.startswith("CUSTOM BASE")
    assert "## About the user" in result


@pytest.mark.asyncio
async def test_empty_user_md_passes_through(_wiki_dir: Path):
    """An empty USER.md should not inject anything."""
    (_wiki_dir / "USER.md").write_text("", encoding="utf-8")
    hook = WikiInjectionHook()
    req = _request("Base.")
    received: list[str] = []

    async def handler(r: ModelRequest) -> AssistantMessage:
        received.append(r.system_prompt)
        return AssistantMessage(content="ok")

    await hook.wrap_model_call(_ctx(), _state(), req, handler)
    assert received[0] == "Base."


# ── BM25 unit tests (used by wiki_search) ────────────────────────────────────


def test_tokenize_basic():
    assert _tokenize("Hello World") == ["hello", "world"]


def test_tokenize_drops_single_char_tokens():
    assert "a" not in _tokenize("a bc def")
    assert "bc" in _tokenize("a bc def")
    assert "def" in _tokenize("a bc def")


def test_score_topics_returns_all_topics():
    topics = [
        WikiFileInfo(
            path="topics/auth.md",
            description="auth strategy",
            updated=None,
            tags=("auth",),
        ),
        WikiFileInfo(
            path="topics/deploy.md",
            description="deployment notes",
            updated=None,
            tags=("deploy",),
        ),
    ]
    results = _score_topics("auth question", topics)
    assert len(results) == 2


def test_score_topics_relevant_scores_higher():
    topics = [
        WikiFileInfo(
            path="topics/auth.md",
            description="JWT authentication strategy",
            updated=None,
            tags=("auth", "jwt"),
        ),
        WikiFileInfo(
            path="topics/deploy.md",
            description="deployment pipeline overview",
            updated=None,
            tags=("deploy",),
        ),
    ]
    results = _score_topics("how does jwt auth work", topics)
    scores = {info.path: score for info, score in results}
    assert scores["topics/auth.md"] > scores["topics/deploy.md"]


def test_score_topics_empty_query_all_zero():
    topics = [
        WikiFileInfo(path="topics/auth.md", description="auth", updated=None, tags=()),
    ]
    results = _score_topics("", topics)
    assert results[0][1] == 0.0


def test_score_topics_tags_weighted_higher_than_description():
    """A single tag match should outscore a single description match."""
    topics = [
        WikiFileInfo(
            path="topics/desc-match.md",
            description="auth related info",
            updated=None,
            tags=(),
        ),
        WikiFileInfo(
            path="topics/tag-match.md",
            description="some topic",
            updated=None,
            tags=("auth",),
        ),
    ]
    results = _score_topics("auth", topics)
    score_map = {info.path: score for info, score in results}
    assert score_map["topics/tag-match.md"] > score_map["topics/desc-match.md"]


def test_tokenize_unicode_emoji():
    result = _tokenize("hello 🚀 world")
    assert "hello" in result
    assert "world" in result


def test_tokenize_numbers_and_mixed():
    result = _tokenize("api2 v3 rest-api")
    assert "api2" in result
    assert "rest" in result
    assert "api" in result


def test_tokenize_very_long_token():
    long_token = "a" * 1000
    result = _tokenize(f"hello {long_token} world")
    assert "hello" in result
    assert "world" in result
    assert long_token in result


def test_tokenize_only_special_chars():
    result = _tokenize("!@#$%^&*()")
    assert result == []


def test_score_topics_filename_stem_contributes():
    topics = [
        WikiFileInfo(path="topics/jwt-auth.md", description="", updated=None, tags=()),
    ]
    results = _score_topics("jwt", topics)
    assert results[0][1] == 0.5


def test_score_topics_multiple_token_matches_accumulate():
    topics = [
        WikiFileInfo(
            path="topics/auth.md",
            description="jwt auth strategy for api",
            updated=None,
            tags=(),
        ),
    ]
    results = _score_topics("jwt auth api", topics)
    assert results[0][1] == 3.5


def test_score_topics_tag_with_multiple_words():
    topics = [
        WikiFileInfo(
            path="topics/api.md",
            description="",
            updated=None,
            tags=("rest-api", "http"),
        ),
    ]
    results = _score_topics("rest api", topics)
    assert results[0][1] == 3.5


def test_score_topics_same_token_in_desc_and_tag():
    topics = [
        WikiFileInfo(
            path="topics/auth.md",
            description="auth strategy",
            updated=None,
            tags=("auth", "security"),
        ),
    ]
    results = _score_topics("auth", topics)
    assert results[0][1] == 3.0


def test_score_topics_threshold_boundary_exactly_0_5():
    topics = [
        WikiFileInfo(path="topics/jwt-auth.md", description="", updated=None, tags=()),
    ]
    results = _score_topics("jwt", topics)
    assert results[0][1] == 0.5
