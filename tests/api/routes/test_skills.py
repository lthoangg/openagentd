"""Tests for /api/skills HTTP routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes.skills import router as skills_router
from app.services import team_manager


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fs_dirs(tmp_path: Path, monkeypatch):
    """Redirect AGENTS_DIR and SKILLS_DIR to an isolated tmp tree."""
    from app.core.config import settings

    agents = tmp_path / "agents"
    skills = tmp_path / "skills"
    agents.mkdir()
    skills.mkdir()
    monkeypatch.setattr(settings, "AGENTS_DIR", str(agents))
    monkeypatch.setattr(settings, "SKILLS_DIR", str(skills))
    return agents, skills


@pytest.fixture
async def client(fs_dirs):
    app = FastAPI()
    app.include_router(skills_router, prefix="/api/skills")
    # Clear any team state that may linger from parallel tests
    await team_manager.stop()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    await team_manager.stop()


# ── Sample skill content ───────────────────────────────────────────────────────

VALID_SKILL = """\
---
name: research
description: A research skill.
---
Do research.
"""

MISMATCHED_NAME_SKILL = """\
---
name: other
description: Mismatch.
---
Body.
"""

NON_DICT_FRONTMATTER_SKILL = """\
---
- item1
- item2
---
Body.
"""

NON_STRING_DESC_SKILL = """\
---
name: research
description: 42
---
Body.
"""

INVALID_YAML_SKILL = """\
---
name: research
description: [unclosed
---
Body.
"""


# ── _parse_skill unit tests (via POST /api/skills validation) ─────────────────


@pytest.mark.asyncio
async def test_create_invalid_yaml_returns_422(client):
    resp = await client.post(
        "/api/skills",
        json={"name": "research", "content": INVALID_YAML_SKILL},
    )
    assert resp.status_code == 422
    assert "frontmatter" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_non_dict_frontmatter_returns_422(client):
    resp = await client.post(
        "/api/skills",
        json={"name": "research", "content": NON_DICT_FRONTMATTER_SKILL},
    )
    assert resp.status_code == 422
    assert "mapping" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_non_string_description_returns_422(client):
    resp = await client.post(
        "/api/skills",
        json={"name": "research", "content": NON_STRING_DESC_SKILL},
    )
    assert resp.status_code == 422
    assert "description" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_name_mismatch_returns_422(client):
    resp = await client.post(
        "/api/skills",
        json={"name": "research", "content": MISMATCHED_NAME_SKILL},
    )
    assert resp.status_code == 422
    assert "other" in resp.json()["detail"]


# ── GET /api/skills ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_skills_empty(client):
    resp = await client.get("/api/skills")
    assert resp.status_code == 200
    assert resp.json() == {"skills": []}


@pytest.mark.asyncio
async def test_list_skills_returns_created_skill(client):
    await client.post("/api/skills", json={"name": "research", "content": VALID_SKILL})
    resp = await client.get("/api/skills")
    assert resp.status_code == 200
    skills = resp.json()["skills"]
    assert len(skills) == 1
    assert skills[0]["name"] == "research"
    assert skills[0]["valid"] is True


@pytest.mark.asyncio
async def test_list_skills_includes_read_error(client, fs_dirs, monkeypatch):
    """A skill whose file is unreadable shows up as invalid instead of crashing."""
    _, skills_dir = fs_dirs
    # Manually create a skill directory but make read_skill raise
    (skills_dir / "broken").mkdir()
    (skills_dir / "broken" / "SKILL.md").write_text("content")

    from app.services import agent_fs

    original_read = agent_fs.read_skill

    def bad_read(name):
        if name == "broken":
            raise OSError("permission denied")
        return original_read(name)

    monkeypatch.setattr(agent_fs, "read_skill", bad_read)

    resp = await client.get("/api/skills")
    assert resp.status_code == 200
    skills = resp.json()["skills"]
    broken = next(s for s in skills if s["name"] == "broken")
    assert broken["valid"] is False
    assert "permission denied" in broken["error"]


# ── GET /api/skills/{name} ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_skill_not_found_returns_404(client):
    resp = await client.get("/api/skills/missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_skill_bad_name_returns_400(client):
    # Names with spaces/special chars fail _validate_name → AgentFsPathError → 400
    resp = await client.get("/api/skills/bad%20name")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_skill_returns_detail(client):
    await client.post("/api/skills", json={"name": "research", "content": VALID_SKILL})
    resp = await client.get("/api/skills/research")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "research"
    assert data["description"] == "A research skill."
    assert "Do research" in data["content"]


# ── POST /api/skills ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_skill_success(client):
    resp = await client.post(
        "/api/skills", json={"name": "research", "content": VALID_SKILL}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "research"
    assert data["description"] == "A research skill."


@pytest.mark.asyncio
async def test_create_skill_conflict_returns_409(client):
    await client.post("/api/skills", json={"name": "research", "content": VALID_SKILL})
    resp = await client.post(
        "/api/skills", json={"name": "research", "content": VALID_SKILL}
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_skill_bad_path_returns_400(client, monkeypatch):
    from app.services import agent_fs
    from app.services.agent_fs import AgentFsPathError

    monkeypatch.setattr(
        agent_fs,
        "write_skill",
        lambda *a, **kw: (_ for _ in ()).throw(AgentFsPathError("bad")),
    )
    resp = await client.post(
        "/api/skills",
        json={"name": "research", "content": VALID_SKILL},
    )
    assert resp.status_code == 400


# ── PUT /api/skills/{name} ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_skill_name_mismatch_returns_422(client):
    await client.post("/api/skills", json={"name": "research", "content": VALID_SKILL})
    resp = await client.put(
        "/api/skills/research",
        json={"name": "other", "content": VALID_SKILL},
    )
    assert resp.status_code == 422
    assert "research" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_skill_invalid_content_returns_422(client):
    await client.post("/api/skills", json={"name": "research", "content": VALID_SKILL})
    resp = await client.put(
        "/api/skills/research",
        json={"name": "research", "content": INVALID_YAML_SKILL},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_skill_success(client):
    await client.post("/api/skills", json={"name": "research", "content": VALID_SKILL})
    updated = VALID_SKILL.replace("A research skill.", "Updated description.")
    resp = await client.put(
        "/api/skills/research",
        json={"name": "research", "content": updated},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated description."


@pytest.mark.asyncio
async def test_update_skill_bad_path_returns_400(client, monkeypatch):
    from app.services import agent_fs
    from app.services.agent_fs import AgentFsPathError

    monkeypatch.setattr(
        agent_fs,
        "write_skill",
        lambda *a, **kw: (_ for _ in ()).throw(AgentFsPathError("bad")),
    )
    resp = await client.put(
        "/api/skills/research",
        json={"name": "research", "content": VALID_SKILL},
    )
    assert resp.status_code == 400


# ── DELETE /api/skills/{name} ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_skill_success(client):
    await client.post("/api/skills", json={"name": "research", "content": VALID_SKILL})
    resp = await client.delete("/api/skills/research")
    assert resp.status_code == 200
    assert resp.json() == {"name": "research"}


@pytest.mark.asyncio
async def test_delete_skill_not_found_returns_404(client):
    resp = await client.delete("/api/skills/missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_skill_bad_path_returns_400(client, monkeypatch):
    from app.services import agent_fs
    from app.services.agent_fs import AgentFsPathError

    monkeypatch.setattr(
        agent_fs,
        "delete_skill",
        lambda *a, **kw: (_ for _ in ()).throw(AgentFsPathError("bad")),
    )
    resp = await client.delete("/api/skills/research")
    assert resp.status_code == 400


# ── Cache invalidation — no team reload, drift detection picks up changes ─────


@pytest.mark.asyncio
async def test_create_skill_invalidates_cache_without_reloading_team(
    client, monkeypatch, fs_dirs
):
    """Skill mutations must invalidate the discovery cache but never reload the team.

    Mid-turn team reloads tear down in-flight tool execution.  Agents
    instead pick up new/updated skills at the start of their next turn
    via the config-stamp drift check.
    """
    invalidated: list[bool] = []
    reload_called: list[bool] = []

    monkeypatch.setattr(
        team_manager,
        "invalidate_skill_cache",
        lambda: invalidated.append(True),
    )
    # Sentinel: if the route accidentally re-introduces a reload call,
    # this will record it.
    monkeypatch.setattr(
        team_manager,
        "reload",
        AsyncMock(side_effect=lambda: reload_called.append(True)),
    )

    resp = await client.post(
        "/api/skills", json={"name": "research", "content": VALID_SKILL}
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "research"
    assert invalidated == [True], "skill cache must be invalidated"
    assert reload_called == [], "team must NOT be reloaded mid-turn"
