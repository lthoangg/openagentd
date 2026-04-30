"""FastAPI dependency providers."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.schemas import ChatForm
from app.core.config import Settings, settings
from app.core.db import async_session_factory, get_session

if TYPE_CHECKING:
    from app.agent.mode.team.team import AgentTeam


# ── Settings ─────────────────────────────────────────────────────────────────


@lru_cache
def get_settings() -> Settings:
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


# ── DB session ────────────────────────────────────────────────────────────────


DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_session_factory


DbSessionFactory = Annotated[
    async_sessionmaker[AsyncSession], Depends(get_session_factory)
]


# ── Team (optional — None when no team is configured) ────────────────────────
# The team's lifecycle and state live in ``app.services.team_manager``; this
# dependency simply exposes the currently-loaded team to route handlers.


def get_team() -> "AgentTeam | None":
    from app.services import team_manager

    return team_manager.current_team()


TeamDep = Annotated["AgentTeam | None", Depends(get_team)]


# ── Form body dependency ──────────────────────────────────────────────────────
# FastAPI < 1.0 cannot combine ``Annotated[Model, Form()]`` with ``File()``
# in the same endpoint.  ``ChatForm.as_form`` works around this by reading
# individual Form() fields and constructing the validated model.

ChatFormDep = Annotated[ChatForm, Depends(ChatForm.as_form)]
