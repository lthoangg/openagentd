"""Scheduler REST API — CRUD + lifecycle actions for ScheduledTask.

Endpoints
---------
POST   /scheduler/tasks                  — create
GET    /scheduler/tasks                  — list
GET    /scheduler/tasks/{task_id}        — get detail
PUT    /scheduler/tasks/{task_id}        — full update
DELETE /scheduler/tasks/{task_id}        — delete
POST   /scheduler/tasks/{task_id}/pause  — pause
POST   /scheduler/tasks/{task_id}/resume — resume
POST   /scheduler/tasks/{task_id}/trigger — fire immediately
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from app.scheduler.models import ScheduledTask
from app.scheduler.schemas import (
    ScheduledTaskCreate,
    ScheduledTaskListResponse,
    ScheduledTaskResponse,
    ScheduledTaskUpdate,
)
from app.scheduler.scheduler import (
    AgentNotInTeamError,
    TaskNotFoundError,
    TaskScheduler,
    task_scheduler,
)

router = APIRouter()


# ── Dependency ────────────────────────────────────────────────────────────────


def get_scheduler() -> TaskScheduler:
    return task_scheduler


# ── Helpers ───────────────────────────────────────────────────────────────────


def _task_or_404(task: ScheduledTask | None) -> ScheduledTask:
    if task is None:
        raise HTTPException(status_code=404, detail="Scheduled task not found.")
    return task


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post(
    "/tasks",
    response_model=ScheduledTaskResponse,
    status_code=201,
    summary="Create a scheduled task",
)
async def create_task(
    body: ScheduledTaskCreate,
    scheduler: TaskScheduler = Depends(get_scheduler),
) -> ScheduledTaskResponse:
    try:
        saved = await scheduler.create(body)
    except AgentNotInTeamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"A task named '{body.name}' already exists.",
        ) from exc

    return ScheduledTaskResponse.model_validate(saved)


@router.get(
    "/tasks",
    response_model=ScheduledTaskListResponse,
    summary="List all scheduled tasks",
)
async def list_tasks(
    scheduler: TaskScheduler = Depends(get_scheduler),
) -> ScheduledTaskListResponse:
    tasks = await scheduler.list_tasks()
    return ScheduledTaskListResponse(
        tasks=[ScheduledTaskResponse.model_validate(t) for t in tasks]
    )


@router.get(
    "/tasks/{task_id}",
    response_model=ScheduledTaskResponse,
    summary="Get a scheduled task",
)
async def get_task(
    task_id: UUID,
    scheduler: TaskScheduler = Depends(get_scheduler),
) -> ScheduledTaskResponse:
    task = _task_or_404(await scheduler.get_task(task_id))
    return ScheduledTaskResponse.model_validate(task)


@router.put(
    "/tasks/{task_id}",
    response_model=ScheduledTaskResponse,
    summary="Update a scheduled task",
)
async def update_task(
    task_id: UUID,
    body: ScheduledTaskUpdate,
    scheduler: TaskScheduler = Depends(get_scheduler),
) -> ScheduledTaskResponse:
    try:
        task = await scheduler.apply_update(task_id, body)
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Scheduled task not found."
        ) from exc
    except AgentNotInTeamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ScheduledTaskResponse.model_validate(task)


@router.delete(
    "/tasks/{task_id}",
    status_code=204,
    summary="Delete a scheduled task",
)
async def delete_task(
    task_id: UUID,
    scheduler: TaskScheduler = Depends(get_scheduler),
) -> None:
    _task_or_404(await scheduler.get_task(task_id))
    await scheduler.remove(task_id)


@router.post(
    "/tasks/{task_id}/pause",
    response_model=ScheduledTaskResponse,
    summary="Pause a scheduled task",
)
async def pause_task(
    task_id: UUID,
    scheduler: TaskScheduler = Depends(get_scheduler),
) -> ScheduledTaskResponse:
    _task_or_404(await scheduler.get_task(task_id))
    task = await scheduler.pause(task_id)
    return ScheduledTaskResponse.model_validate(task)


@router.post(
    "/tasks/{task_id}/resume",
    response_model=ScheduledTaskResponse,
    summary="Resume a paused scheduled task",
)
async def resume_task(
    task_id: UUID,
    scheduler: TaskScheduler = Depends(get_scheduler),
) -> ScheduledTaskResponse:
    _task_or_404(await scheduler.get_task(task_id))
    task = await scheduler.resume(task_id)
    return ScheduledTaskResponse.model_validate(task)


@router.post(
    "/tasks/{task_id}/trigger",
    status_code=202,
    summary="Fire a task immediately",
)
async def trigger_task(
    task_id: UUID,
    scheduler: TaskScheduler = Depends(get_scheduler),
) -> dict[str, str]:
    _task_or_404(await scheduler.get_task(task_id))
    await scheduler.trigger(task_id)
    return {"status": "dispatched"}
