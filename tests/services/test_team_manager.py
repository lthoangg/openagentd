"""Tests for app.services.team_manager — lifecycle: start, stop, reload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import team_manager


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_team(name: str = "lead") -> MagicMock:
    team = MagicMock()
    team.start = AsyncMock()
    team.stop = AsyncMock()
    team.lead = MagicMock()
    team.lead.name = name
    team.members = {}
    # Snapshot helpers used by _team_snapshot
    agent = MagicMock()
    agent.name = name
    agent.description = "desc"
    agent.model_id = "zai:glm"
    agent._tools = {}
    agent.skills = []
    agent.system_prompt = "sys"
    team.lead.agent = agent
    return team


@pytest.fixture(autouse=True)
async def reset_team_manager():
    """Ensure team_manager._team is None before and after each test."""
    await team_manager.stop()
    yield
    await team_manager.stop()


# ── start() ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_returns_none_when_no_agents(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AGENTS_DIR", str(tmp_path / "empty"))
    result = await team_manager.start()
    assert result is None
    assert team_manager.current_team() is None


@pytest.mark.asyncio
async def test_start_loads_and_starts_team(monkeypatch):
    fake_team = _make_team()

    monkeypatch.setattr(
        "app.services.team_manager.load_team_from_dir", lambda _: fake_team
    )

    result = await team_manager.start()

    assert result is fake_team
    fake_team.start.assert_awaited_once()
    assert team_manager.current_team() is fake_team


@pytest.mark.asyncio
async def test_start_is_idempotent(monkeypatch):
    """Second call to start() while team is running returns the same team."""
    fake_team = _make_team()
    monkeypatch.setattr(
        "app.services.team_manager.load_team_from_dir", lambda _: fake_team
    )

    first = await team_manager.start()
    second = await team_manager.start()

    assert first is second
    # start() on the underlying team should only have been called once
    fake_team.start.assert_awaited_once()


# ── stop() ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_clears_team(monkeypatch):
    fake_team = _make_team()
    monkeypatch.setattr(
        "app.services.team_manager.load_team_from_dir", lambda _: fake_team
    )

    await team_manager.start()
    assert team_manager.current_team() is not None

    await team_manager.stop()
    assert team_manager.current_team() is None
    fake_team.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_when_no_team_is_noop():
    # No exception should be raised when called with no active team
    await team_manager.stop()
    assert team_manager.current_team() is None


@pytest.mark.asyncio
async def test_stop_swallows_exception_from_team_stop(monkeypatch):
    """stop() logs the exception but still clears the team reference."""
    fake_team = _make_team()
    fake_team.stop = AsyncMock(side_effect=RuntimeError("teardown failed"))

    monkeypatch.setattr(
        "app.services.team_manager.load_team_from_dir", lambda _: fake_team
    )
    await team_manager.start()

    # Should not raise even though team.stop() blows up
    await team_manager.stop()

    # Team reference must be cleared despite the error
    assert team_manager.current_team() is None


# ── reload() ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reload_raises_when_no_agents_found(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AGENTS_DIR", str(tmp_path / "empty"))
    monkeypatch.setattr("app.services.team_manager.load_team_from_dir", lambda _: None)

    with pytest.raises(ValueError, match="No agents found"):
        await team_manager.reload()


@pytest.mark.asyncio
async def test_reload_swaps_in_new_team(monkeypatch):
    old_team = _make_team("old-lead")
    new_team = _make_team("new-lead")

    call_count = 0

    def fake_load(_):
        nonlocal call_count
        call_count += 1
        return old_team if call_count == 1 else new_team

    monkeypatch.setattr("app.services.team_manager.load_team_from_dir", fake_load)

    await team_manager.start()
    assert team_manager.current_team() is old_team

    diff = await team_manager.reload()

    assert team_manager.current_team() is new_team
    old_team.stop.assert_awaited_once()
    new_team.start.assert_awaited_once()
    assert diff.lead == "new-lead"


@pytest.mark.asyncio
async def test_reload_keeps_new_team_even_when_old_stop_raises(monkeypatch):
    """Old team's stop() error must not prevent new team from going live."""
    old_team = _make_team("old-lead")
    old_team.stop = AsyncMock(side_effect=RuntimeError("stop error"))
    new_team = _make_team("new-lead")

    call_count = 0

    def fake_load(_):
        nonlocal call_count
        call_count += 1
        return old_team if call_count == 1 else new_team

    monkeypatch.setattr("app.services.team_manager.load_team_from_dir", fake_load)

    await team_manager.start()

    # Should not raise; new team should be live
    diff = await team_manager.reload()

    assert team_manager.current_team() is new_team
    assert diff.lead == "new-lead"


@pytest.mark.asyncio
async def test_reload_leaves_old_team_on_validation_failure(monkeypatch):
    """If load_team_from_dir raises, the running team is untouched."""
    old_team = _make_team("old-lead")

    call_count = 0

    def fake_load(_):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return old_team
        raise ValueError("bad config file")

    monkeypatch.setattr("app.services.team_manager.load_team_from_dir", fake_load)

    await team_manager.start()

    with pytest.raises(ValueError, match="bad config file"):
        await team_manager.reload()

    # Old team must still be running
    assert team_manager.current_team() is old_team
    old_team.stop.assert_not_awaited()
