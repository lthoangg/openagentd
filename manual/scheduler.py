"""Smoke-test the scheduler API.

Usage:
  uv run python -m manual.scheduler list
  uv run python -m manual.scheduler create --agent <name> --type every --every 60 --prompt "Say hello"
  uv run python -m manual.scheduler create --agent <name> --type cron --cron "*/5 * * * *" --prompt "Ping"
  uv run python -m manual.scheduler create --agent <name> --type at --at "2099-01-01T00:00:00Z" --prompt "Future"
  uv run python -m manual.scheduler trigger <TASK_ID>
  uv run python -m manual.scheduler pause   <TASK_ID>
  uv run python -m manual.scheduler resume  <TASK_ID>
  uv run python -m manual.scheduler delete  <TASK_ID>
  uv run python -m manual.scheduler demo    --agent <name>   # create + trigger + list + delete
"""

from __future__ import annotations

import argparse
import json
import time

import httpx

BASE = "http://localhost:8000/api"


# ── helpers ───────────────────────────────────────────────────────────────────


def _get(base: str, path: str) -> dict:
    r = httpx.get(f"{base}{path}")
    r.raise_for_status()
    return r.json()


def _post(base: str, path: str, body: dict | None = None) -> dict:
    r = httpx.post(f"{base}{path}", json=body)
    r.raise_for_status()
    return r.json()


def _delete(base: str, path: str) -> None:
    r = httpx.delete(f"{base}{path}")
    r.raise_for_status()


def _print_task(task: dict, *, indent: str = "") -> None:
    nf = task.get("next_fire_at") or "-"
    lr = task.get("last_run_at") or "-"
    err = task.get("last_error") or ""
    print(
        f"{indent}[{task['status']:9}] {task['name']!r:30}"
        f"  agent={task['agent']}"
        f"  type={task['schedule_type']}"
        f"  runs={task['run_count']}"
        f"  next={nf}"
    )
    if task.get("cron_expression"):
        print(f"{indent}           cron={task['cron_expression']}  tz={task['timezone']}")
    elif task.get("every_seconds"):
        print(f"{indent}           every={task['every_seconds']}s")
    elif task.get("at_datetime"):
        print(f"{indent}           at={task['at_datetime']}")
    print(f"{indent}           prompt={task['prompt'][:80]!r}")
    print(f"{indent}           last_run={lr}")
    if err:
        print(f"{indent}           error={err}")


# ── commands ──────────────────────────────────────────────────────────────────


def cmd_list(base: str) -> None:
    data = _get(base, "/scheduler/tasks")
    tasks = data.get("tasks", [])
    if not tasks:
        print("no scheduled tasks")
        return
    print(f"{len(tasks)} task(s):")
    for t in tasks:
        _print_task(t, indent="  ")
        print()


def cmd_create(base: str, args: argparse.Namespace) -> dict:
    body: dict = {
        "name": args.name,
        "agent": args.agent,
        "schedule_type": args.type,
        "prompt": args.prompt,
        "timezone": args.timezone,
    }
    if args.type == "at":
        body["at_datetime"] = args.at
    elif args.type == "every":
        body["every_seconds"] = int(args.every)
    elif args.type == "cron":
        body["cron_expression"] = args.cron
    if args.session:
        body["session_id"] = args.session

    task = _post(base, "/scheduler/tasks", body)
    print("created:")
    _print_task(task, indent="  ")
    return task


def cmd_trigger(base: str, task_id: str) -> None:
    result = _post(base, f"/scheduler/tasks/{task_id}/trigger")
    print(f"triggered: {result}")


def cmd_pause(base: str, task_id: str) -> None:
    task = _post(base, f"/scheduler/tasks/{task_id}/pause")
    print(f"paused: status={task['status']}")


def cmd_resume(base: str, task_id: str) -> None:
    task = _post(base, f"/scheduler/tasks/{task_id}/resume")
    print(f"resumed: status={task['status']}  next_fire_at={task.get('next_fire_at')}")


def cmd_delete(base: str, task_id: str) -> None:
    _delete(base, f"/scheduler/tasks/{task_id}")
    print(f"deleted {task_id}")


def cmd_demo(base: str, args: argparse.Namespace) -> None:
    """Create an 'every 999s' task, trigger it, wait 2s, list, then delete."""
    import uuid

    unique = uuid.uuid4().hex[:6]
    name = f"demo-{unique}"

    print(f"--- demo: creating task '{name}' ---")
    body = {
        "name": name,
        "agent": args.agent,
        "schedule_type": "every",
        "every_seconds": 999,
        "prompt": "This is a scheduler demo. Reply with just: SCHEDULER_OK",
        "timezone": "UTC",
    }
    task = _post(base, "/scheduler/tasks", body)
    task_id = task["id"]
    print(f"  created id={task_id}")

    print("--- triggering immediately ---")
    _post(base, f"/scheduler/tasks/{task_id}/trigger")
    print("  dispatched (agent is running in background)")

    print("--- waiting 3s for run_count to increment ---")
    time.sleep(3)

    print("--- listing tasks ---")
    cmd_list(base)

    print(f"--- deleting demo task {task_id} ---")
    _delete(base, f"/scheduler/tasks/{task_id}")
    print("  done")


# ── entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description="Scheduler API smoke tests")
    p.add_argument("--base", default=BASE)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all scheduled tasks")

    cr = sub.add_parser("create", help="Create a scheduled task")
    cr.add_argument("--name", default=None, help="Task name (auto-generated if omitted)")
    cr.add_argument("--agent", required=True, help="Agent name")
    cr.add_argument("--type", choices=["at", "every", "cron"], required=True, dest="type")
    cr.add_argument("--at", default=None, help="ISO-8601 datetime for 'at' type")
    cr.add_argument("--every", default=None, help="Interval in seconds for 'every' type")
    cr.add_argument("--cron", default=None, help="5-field cron expression")
    cr.add_argument("--timezone", default="UTC")
    cr.add_argument("--prompt", required=True, help="Prompt to send to the agent")
    cr.add_argument("--session", default=None, help="session_id (omit=new, 'auto'=persistent)")

    tr = sub.add_parser("trigger", help="Fire a task immediately")
    tr.add_argument("task_id")

    pa = sub.add_parser("pause", help="Pause a task")
    pa.add_argument("task_id")

    re = sub.add_parser("resume", help="Resume a paused task")
    re.add_argument("task_id")

    de = sub.add_parser("delete", help="Delete a task")
    de.add_argument("task_id")

    dm = sub.add_parser("demo", help="End-to-end demo: create + trigger + list + delete")
    dm.add_argument("--agent", required=True, help="Agent name for the demo task")

    args = p.parse_args()
    base = args.base.rstrip("/")

    # auto-generate name for create
    if args.cmd == "create" and args.name is None:
        import uuid
        args.name = f"task-{uuid.uuid4().hex[:6]}"

    try:
        if args.cmd == "list":
            cmd_list(base)
        elif args.cmd == "create":
            cmd_create(base, args)
        elif args.cmd == "trigger":
            cmd_trigger(base, args.task_id)
        elif args.cmd == "pause":
            cmd_pause(base, args.task_id)
        elif args.cmd == "resume":
            cmd_resume(base, args.task_id)
        elif args.cmd == "delete":
            cmd_delete(base, args.task_id)
        elif args.cmd == "demo":
            cmd_demo(base, args)
    except httpx.HTTPStatusError as e:
        print(f"HTTP {e.response.status_code}: {e.response.text}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
