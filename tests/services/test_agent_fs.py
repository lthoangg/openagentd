"""Tests for the ``agent_fs`` filesystem service."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import agent_fs
from app.services.agent_fs import (
    AgentFsConflictError,
    AgentFsNotFoundError,
    AgentFsPathError,
)


@pytest.fixture
def fs_dirs(tmp_path: Path, monkeypatch):
    """Redirect AGENTS_DIR and SKILLS_DIR to a temp directory per test."""
    from app.core.config import settings

    agents = tmp_path / "agents"
    skills = tmp_path / "skills"
    agents.mkdir()
    skills.mkdir()
    monkeypatch.setattr(settings, "AGENTS_DIR", str(agents))
    monkeypatch.setattr(settings, "SKILLS_DIR", str(skills))
    return agents, skills


# ── Agents ───────────────────────────────────────────────────────────────────


def test_list_agents_empty(fs_dirs):
    assert agent_fs.list_agents() == []


def test_write_and_read_agent(fs_dirs):
    agents_dir, _ = fs_dirs
    record = agent_fs.write_agent("alpha", "---\nname: alpha\n---\nhi\n", create=True)
    assert Path(record.path) == agents_dir / "alpha.md"
    assert (agents_dir / "alpha.md").read_text() == "---\nname: alpha\n---\nhi\n"

    read = agent_fs.read_agent("alpha")
    assert read.name == "alpha"
    assert "hi" in read.content


def test_write_agent_create_conflict(fs_dirs):
    agent_fs.write_agent("alpha", "x", create=True)
    with pytest.raises(AgentFsConflictError):
        agent_fs.write_agent("alpha", "y", create=True)


def test_write_agent_update_allows_overwrite(fs_dirs):
    agent_fs.write_agent("alpha", "v1", create=True)
    agent_fs.write_agent("alpha", "v2", create=False)
    assert agent_fs.read_agent("alpha").content == "v2"


def test_delete_agent(fs_dirs):
    agent_fs.write_agent("alpha", "x", create=True)
    agent_fs.delete_agent("alpha")
    assert agent_fs.list_agents() == []
    with pytest.raises(AgentFsNotFoundError):
        agent_fs.read_agent("alpha")


def test_read_agent_not_found(fs_dirs):
    with pytest.raises(AgentFsNotFoundError):
        agent_fs.read_agent("missing")


@pytest.mark.parametrize(
    "bad_name",
    [
        "",
        "../evil",
        "a/b",
        "a\\b",
        ".hidden",
        "x y",
        "a" * 70,
    ],
)
def test_invalid_name_rejected(fs_dirs, bad_name):
    with pytest.raises(AgentFsPathError):
        agent_fs.read_agent(bad_name)


def test_list_agents_sorted(fs_dirs):
    agent_fs.write_agent("beta", "x", create=True)
    agent_fs.write_agent("alpha", "x", create=True)
    agent_fs.write_agent("gamma", "x", create=True)
    assert agent_fs.list_agents() == ["alpha", "beta", "gamma"]


# ── Skills ───────────────────────────────────────────────────────────────────


def test_write_and_read_skill(fs_dirs):
    _, skills_dir = fs_dirs
    record = agent_fs.write_skill(
        "research", "---\nname: research\n---\nbody\n", create=True
    )
    assert Path(record.path) == skills_dir / "research" / "SKILL.md"
    assert (skills_dir / "research" / "SKILL.md").read_text() == (
        "---\nname: research\n---\nbody\n"
    )


def test_list_skills_only_dirs_with_skill_md(fs_dirs):
    _, skills_dir = fs_dirs
    agent_fs.write_skill("a", "x", create=True)
    # Empty dir should not show up.
    (skills_dir / "empty").mkdir()
    # Dir with a non-SKILL.md file should also not show up.
    (skills_dir / "other").mkdir()
    (skills_dir / "other" / "notes.md").write_text("x")
    assert agent_fs.list_skills() == ["a"]


def test_delete_skill_removes_empty_dir(fs_dirs):
    _, skills_dir = fs_dirs
    agent_fs.write_skill("a", "x", create=True)
    agent_fs.delete_skill("a")
    assert not (skills_dir / "a").exists()


def test_delete_skill_preserves_dir_with_siblings(fs_dirs):
    _, skills_dir = fs_dirs
    agent_fs.write_skill("a", "x", create=True)
    (skills_dir / "a" / "notes.md").write_text("extra")
    agent_fs.delete_skill("a")
    assert (skills_dir / "a").exists()
    assert not (skills_dir / "a" / "SKILL.md").exists()


def test_delete_skill_not_found(fs_dirs):
    with pytest.raises(AgentFsNotFoundError):
        agent_fs.delete_skill("missing")
