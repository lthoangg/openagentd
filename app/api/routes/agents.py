"""Agent CRUD: writes ``.md`` files under ``AGENTS_DIR``.

Validates each write against ``AgentConfig`` and team invariants
(one lead, known tools, valid models).  Failed validation rolls the
file back.  Running agents pick up new config on their next turn.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import ValidationError

from app.agent.loader import AgentConfig
from app.agent.providers.capabilities import (
    _PREFIX_FALLBACKS,
    _load_exact_models,
    get_capabilities,
)
from app.agent.tools.builtin.skill import discover_skills
from app.api.schemas.agents import (
    AgentDeleteResponse,
    AgentDetail,
    AgentListResponse,
    AgentSummary,
    AgentWriteRequest,
    ModelCatalogEntry,
    RegistryResponse,
    SkillCatalogEntry,
    ToolCatalogEntry,
)
from app.services import agent_fs
from app.services.agent_fs import (
    AgentFsConflictError,
    AgentFsNotFoundError,
    AgentFsPathError,
)

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────


def _parse_summary(name: str, content: str) -> AgentSummary:
    """Never raises; invalid agents are flagged via ``valid=False``."""
    try:
        cfg = _parse_content(name, content)
    except ValueError as exc:
        return AgentSummary(
            name=name,
            role="member",
            description=None,
            model=None,
            tools=[],
            skills=[],
            valid=False,
            error=str(exc),
        )
    return AgentSummary(
        name=cfg.name,
        role=cfg.role,
        description=cfg.description,
        model=cfg.model,
        tools=cfg.tools,
        skills=cfg.skills,
        valid=True,
        error=None,
    )


def _parse_content(name: str, content: str) -> AgentConfig:
    """Parse raw .md text into an ``AgentConfig`` (no disk I/O)."""
    from app.agent.loader import _FRONTMATTER_RE

    m = _FRONTMATTER_RE.match(content)
    if not m:
        raise ValueError(
            "Missing YAML frontmatter. Expected '---\\n<yaml>\\n---\\n<system prompt>'."
        )
    import yaml

    try:
        raw_meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML frontmatter: {exc}") from exc
    if not isinstance(raw_meta, dict):
        raise ValueError("Frontmatter must be a YAML mapping.")
    body = m.group(2).strip()
    raw_meta.setdefault("name", name)
    raw_meta["system_prompt"] = body or "You are a helpful assistant."
    try:
        return AgentConfig.model_validate(raw_meta)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise ValueError(errors) from exc


def _require_frontmatter_name(name: str, content: str) -> None:
    cfg = _parse_content(name, content)
    if cfg.name != name:
        raise HTTPException(
            status_code=422,
            detail=(f"Frontmatter name '{cfg.name}' does not match URL name '{name}'."),
        )


async def _validate_or_restore(
    rollback_name: str | None, rollback_content: str | None
) -> None:
    """Re-validate the agents directory; roll back on failure.

    ``rollback_content=None`` → delete the just-created file; otherwise
    restore the previous text.
    """
    from app.agent.loader import load_team_from_dir
    from app.core.config import settings as _settings

    try:
        candidate = load_team_from_dir(_settings.AGENTS_DIR)
        if candidate is None:
            raise ValueError(
                f"No agents would remain in '{_settings.AGENTS_DIR}'. "
                "At least one .md file with 'role: lead' is required."
            )
    except ValueError as exc:
        if rollback_name is not None and rollback_content is not None:
            try:
                try:
                    agent_fs.write_agent(rollback_name, rollback_content, create=True)
                except agent_fs.AgentFsConflictError:
                    agent_fs.write_agent(rollback_name, rollback_content, create=False)
            except Exception:
                logger.exception("agents_rollback_failed name={}", rollback_name)
        elif rollback_name is not None and rollback_content is None:
            try:
                agent_fs.delete_agent(rollback_name)
            except Exception:
                logger.exception("agents_rollback_delete_failed name={}", rollback_name)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("")
async def list_agents() -> AgentListResponse:
    rows: list[AgentSummary] = []
    for name in agent_fs.list_agents():
        try:
            record = agent_fs.read_agent(name)
        except Exception as exc:
            rows.append(
                AgentSummary(
                    name=name,
                    role="member",
                    valid=False,
                    error=str(exc),
                )
            )
            continue
        rows.append(_parse_summary(name, record.content))
    return AgentListResponse(agents=rows)


@router.get("/registry")
async def get_registry() -> RegistryResponse:
    """Dropdown catalog: tools, skills, providers, known models."""
    from app.agent.loader import _default_tool_registry

    tool_registry = _default_tool_registry()
    tools = sorted(
        (
            ToolCatalogEntry(name=t.name, description=t.description or "")
            for t in tool_registry.values()
        ),
        key=lambda t: t.name,
    )

    skill_map = discover_skills()
    skills = sorted(
        (
            SkillCatalogEntry(name=k, description=v.get("description", ""))
            for k, v in skill_map.items()
        ),
        key=lambda s: s.name,
    )

    providers = sorted({p.rstrip(":") for p, _ in _PREFIX_FALLBACKS})

    exact = _load_exact_models()
    models: list[ModelCatalogEntry] = []
    for model_id in sorted(exact.keys()):
        if ":" not in model_id:
            continue
        provider, model = model_id.split(":", 1)
        caps = get_capabilities(model_id)
        models.append(
            ModelCatalogEntry(
                id=model_id,
                provider=provider,
                model=model,
                vision=caps.input.vision,
            )
        )

    return RegistryResponse(
        tools=tools,
        skills=skills,
        providers=providers,
        models=models,
    )


@router.get("/{name}")
async def get_agent(name: str) -> AgentDetail:
    try:
        record = agent_fs.read_agent(name)
    except AgentFsPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AgentFsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    config: dict[str, Any] | None = None
    error: str | None = None
    try:
        cfg = _parse_content(name, record.content)
        config = cfg.model_dump(exclude_none=True)
    except ValueError as exc:
        error = str(exc)

    return AgentDetail(
        name=record.name,
        path=record.path,
        content=record.content,
        config=config,
        error=error,
    )


@router.post("", status_code=201)
async def create_agent(body: AgentWriteRequest) -> AgentDetail:
    try:
        cfg = _parse_content(body.name, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if cfg.name != body.name:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Frontmatter name '{cfg.name}' must match the request name "
                f"'{body.name}'."
            ),
        )

    try:
        record = agent_fs.write_agent(body.name, body.content, create=True)
    except AgentFsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AgentFsPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _validate_or_restore(rollback_name=body.name, rollback_content=None)

    return AgentDetail(
        name=record.name,
        path=record.path,
        content=record.content,
        config=cfg.model_dump(exclude_none=True),
    )


@router.put("/{name}")
async def update_agent(name: str, body: AgentWriteRequest) -> AgentDetail:
    if body.name != name:
        raise HTTPException(
            status_code=422,
            detail=f"URL name '{name}' does not match body name '{body.name}'.",
        )

    try:
        previous = agent_fs.read_agent(name)
    except AgentFsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AgentFsPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        cfg = _parse_content(name, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _require_frontmatter_name(name, body.content)

    try:
        record = agent_fs.write_agent(name, body.content, create=False)
    except AgentFsPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _validate_or_restore(rollback_name=name, rollback_content=previous.content)

    return AgentDetail(
        name=record.name,
        path=record.path,
        content=record.content,
        config=cfg.model_dump(exclude_none=True),
    )


@router.delete("/{name}")
async def delete_agent(name: str) -> AgentDeleteResponse:
    """422 if removal would leave the team without a lead."""
    try:
        previous = agent_fs.read_agent(name)
    except AgentFsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AgentFsPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        agent_fs.delete_agent(name)
    except AgentFsPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _validate_or_restore(rollback_name=name, rollback_content=previous.content)
    return AgentDeleteResponse(name=name)
