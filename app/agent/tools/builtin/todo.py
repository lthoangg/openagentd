"""todo_manage — structured task list for the agent.

Accepts a list of actions executed in order in a single call:

* ``create`` — add a new item; returns an auto-generated ``task_id`` (``task_1``, ``task_2``, …).
* ``update`` — mutate an existing item by ``task_id``.
* ``delete`` — remove an item by ``task_id``.
* ``read``   — return the full list with ``task_id``s (useful as the sole action).

Storage
-------
Items are written to ``.todos.json`` inside the sandbox workspace:

.. code-block:: json

    {
        "counter": 3,
        "items": [
            {"task_id": "task_1", "content": "…", "status": "completed", "priority": "high"},
            {"task_id": "task_2", "content": "…", "status": "in_progress", "priority": "medium"}
        ]
    }

``counter`` is monotonically increasing; new items get ``task_{counter + 1}``
and the counter is incremented atomically with the write.

Within a turn the store is also cached in ``state.metadata["_todos"]`` to
avoid redundant disk reads.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from app.agent.sandbox import get_sandbox
from app.agent.tools.registry import InjectedArg, Tool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Filename for the per-workspace todo store.  Public so the
#: ``/team/sessions/{id}/todos`` endpoint can locate the same file.
TODOS_FILENAME = ".todos.json"

# ---------------------------------------------------------------------------
# Action models (discriminated union on "action")
# ---------------------------------------------------------------------------


class CreateAction(BaseModel):
    action: Literal["create"]
    content: str = Field(description="Brief description of the task.")
    status: Literal["pending", "in_progress", "completed", "cancelled"] = Field(
        description="Initial status.",
    )
    priority: Literal["high", "medium", "low"] = Field(
        description="Priority level.",
    )


class UpdateAction(BaseModel):
    action: Literal["update"]
    task_id: str = Field(description="ID of the task to update (e.g. task_1).")
    content: str | None = Field(
        default=None, description="New description (omit to keep unchanged)."
    )
    status: Literal["pending", "in_progress", "completed", "cancelled"] | None = Field(
        default=None, description="New status (omit to keep unchanged)."
    )
    priority: Literal["high", "medium", "low"] | None = Field(
        default=None, description="New priority (omit to keep unchanged)."
    )


class DeleteAction(BaseModel):
    action: Literal["delete"]
    task_id: str = Field(description="ID of the task to remove (e.g. task_1).")


class ReadAction(BaseModel):
    action: Literal["read"]


AnyAction = Annotated[
    CreateAction | UpdateAction | DeleteAction | ReadAction,
    Field(discriminator="action"),
]

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _todos_path() -> Any:
    sandbox = get_sandbox()
    return sandbox.workspace_root / TODOS_FILENAME


def _load_store() -> dict:
    """Return ``{"counter": int, "items": list[dict]}``."""
    path = _todos_path()
    if not path.exists():
        return {"counter": 0, "items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "items" in data:
            return data
    except Exception:
        pass
    return {"counter": 0, "items": []}


def _save_store(store: dict) -> None:
    path = _todos_path()
    path.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")


def _format_items(items: list[dict]) -> str:
    if not items:
        return "No todos."
    lines: list[str] = []
    for item in items:
        lines.append(
            f"[{item['task_id']}] [{item['status']}] ({item['priority']}) {item['content']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

_DESCRIPTION = """\
Manage the structured task list. Pass one or more actions in a single call;
they are executed in order.

Actions
-------
create  — Add a new task (returns the assigned task_id).
update  — Update an existing task by task_id (change any combination of
          content, status, priority).
delete  — Remove a task permanently by task_id.
read    — Return the full task list with task_ids.

Rules
-----
- Batch related changes into a single call (e.g. complete the current task
  and start the next one together).
- Only ONE task should be in_progress at a time.
- Mark tasks completed immediately when done; do not batch updates across turns.
- Use status=cancelled for tasks that are no longer needed instead of deleting.
- Skip this tool for single, trivial tasks.\
"""


async def _todo_manage(
    actions: Annotated[
        list[AnyAction],
        Field(description="Ordered list of actions to execute."),
    ],
    _state: Annotated[Any, InjectedArg()] = None,
) -> str:
    store = _load_store()
    if _state is not None and "_todos" in _state.metadata:
        store = _state.metadata["_todos"]

    log_parts: list[str] = []

    for act in actions:
        if isinstance(act, ReadAction):
            # read is a no-op on the store — result is returned at the end
            pass

        elif isinstance(act, CreateAction):
            store["counter"] += 1
            new_id = f"task_{store['counter']}"
            store["items"].append(
                {
                    "task_id": new_id,
                    "content": act.content,
                    "status": act.status,
                    "priority": act.priority,
                }
            )
            log_parts.append(f"created {new_id}")

        elif isinstance(act, UpdateAction):
            for item in store["items"]:
                if item["task_id"] == act.task_id:
                    if act.content is not None:
                        item["content"] = act.content
                    if act.status is not None:
                        item["status"] = act.status
                    if act.priority is not None:
                        item["priority"] = act.priority
                    log_parts.append(f"updated {act.task_id}")
                    break
            else:
                log_parts.append(f"not_found {act.task_id}")

        elif isinstance(act, DeleteAction):
            before = len(store["items"])
            store["items"] = [i for i in store["items"] if i["task_id"] != act.task_id]
            if len(store["items"]) < before:
                log_parts.append(f"deleted {act.task_id}")
            else:
                log_parts.append(f"not_found {act.task_id}")

    _save_store(store)
    if _state is not None:
        _state.metadata["_todos"] = store

    logger.info(
        "todo_manage actions=[{}]", ", ".join(log_parts) if log_parts else "read"
    )
    return _format_items(store["items"])


todo_manage = Tool(
    _todo_manage,
    name="todo_manage",
    description=_DESCRIPTION,
)
