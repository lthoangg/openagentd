"""Inspect and trigger the dream agent.

Shows unprocessed sessions/notes, triggers dream processing, and displays
the processing log. Reads the DB directly — no server required for status
and log commands. The `run` command calls POST /api/dream/run (server required).

Usage:
  uv run python -m manual.dream status            # what hasn't been processed yet
  uv run python -m manual.dream run               # trigger dream via API
  uv run python -m manual.dream run --direct      # trigger dream directly (no server)
  uv run python -m manual.dream log               # show dream_log entries
  uv run python -m manual.dream log --notes       # show dream_notes_log entries
  uv run python -m manual.dream log --all         # show both logs
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import timezone

import httpx
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.chat import ChatSession, DreamLog, DreamNotesLog
from app.services.wiki import NOTES_DIR, wiki_root


def _db_url() -> str:
    return settings.DATABASE_URL.get_secret_value()


# ── Status ────────────────────────────────────────────────────────────────────


async def cmd_status() -> None:
    """Show unprocessed sessions and note files."""
    engine = create_async_engine(_db_url())

    try:
        async with AsyncSession(engine) as db:
            return await _cmd_status_inner(db)
    except Exception as exc:
        if "no such table" in str(exc):
            print("Database tables not found — run the server once to apply migrations.")
            print("  make dev   # starts server, runs migrations")
            return
        raise


async def _cmd_status_inner(db: AsyncSession) -> None:
    """Inner status logic after DB is confirmed available."""
    # Unprocessed sessions
    processed_ids_result = await db.exec(select(DreamLog.session_id))
    processed_ids = set(processed_ids_result.all())

    all_sessions_result = await db.exec(
        select(ChatSession).order_by(ChatSession.created_at)
    )
    all_sessions = all_sessions_result.all()

    unprocessed_sessions = [s for s in all_sessions if s.id not in processed_ids]

    # Unprocessed notes
    root = wiki_root()
    notes_dir = root / NOTES_DIR
    all_notes: list[str] = []
    if notes_dir.is_dir():
        all_notes = sorted(
            e.name for e in notes_dir.iterdir()
            if e.is_file() and e.suffix == ".md"
        )

    processed_notes_result = await db.exec(select(DreamNotesLog.filename))
    processed_notes = set(processed_notes_result.all())
    unprocessed_notes = [n for n in all_notes if n not in processed_notes]

    print(f"\nWiki root: {wiki_root()}")
    print()

    # Sessions
    total_sessions = len(all_sessions)
    print(f"Sessions: {len(unprocessed_sessions)} unprocessed / {total_sessions} total")
    if unprocessed_sessions:
        print()
        for s in unprocessed_sessions:
            ts = str(s.created_at)[:19] if s.created_at else "?"
            agent = s.agent_name or "unknown"
            title = (s.title or "(no title)")[:50]
            print(f"  {s.id}  {ts}  {agent:16s}  {title}")
    else:
        print("  (all sessions processed)")

    print()

    # Notes
    total_notes = len(all_notes)
    print(f"Notes: {len(unprocessed_notes)} unprocessed / {total_notes} total")
    if unprocessed_notes:
        print()
        for n in unprocessed_notes:
            path = notes_dir / n
            size = path.stat().st_size if path.exists() else 0
            print(f"  {n}  ({size} bytes)")
    else:
        print("  (all notes processed)")

    print()


# ── Run ───────────────────────────────────────────────────────────────────────


async def cmd_run(*, base_url: str, direct: bool) -> None:
    """Trigger dream processing."""
    if direct:
        await _run_direct()
    else:
        await _run_via_api(base_url)


async def _run_via_api(base_url: str) -> None:
    url = f"{base_url}/dream/run"
    print(f"POST {url}")
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(url)
            resp.raise_for_status()
            result = resp.json()
            print(f"\nResult: {json.dumps(result, indent=2)}")
        except httpx.HTTPStatusError as exc:
            print(f"HTTP error {exc.response.status_code}: {exc.response.text}")
        except httpx.ConnectError:
            print(f"Could not connect to {url} — is the server running?")
            print("Use --direct to run without the server.")


async def _run_direct() -> None:
    from app.services.dream import run_dream

    engine = create_async_engine(_db_url())
    print("Running dream directly (no server)...")
    async with AsyncSession(engine) as db:
        result = await run_dream(db)
    print(f"\nResult: {json.dumps(result, indent=2)}")


# ── Log ───────────────────────────────────────────────────────────────────────


async def cmd_log(*, show_sessions: bool, show_notes: bool) -> None:
    """Show dream processing log."""
    engine = create_async_engine(_db_url())

    async with AsyncSession(engine) as db:
        if show_sessions:
            result = await db.exec(
                select(DreamLog).order_by(DreamLog.processed_at)
            )
            entries = result.all()

            print(f"\nDream log ({len(entries)} sessions processed)")
            if entries:
                print(f"\n  {'processed_at':22s}  {'session_id':36s}  {'agent':16s}  topics")
                print("  " + "-" * 100)
                for e in entries:
                    ts = str(e.processed_at.astimezone(timezone.utc))[:19] if e.processed_at else "?"
                    topics = json.loads(e.topics_written) if e.topics_written else []
                    topics_str = ", ".join(topics) if topics else "(none)"
                    agent = e.agent_name or "?"
                    print(f"  {ts:22s}  {e.session_id!s:36s}  {agent:16s}  {topics_str}")
            else:
                print("  (empty)")

        if show_notes:
            result = await db.exec(
                select(DreamNotesLog).order_by(DreamNotesLog.processed_at)
            )
            entries = result.all()

            print(f"\nDream notes log ({len(entries)} notes processed)")
            if entries:
                print(f"\n  {'processed_at':22s}  filename")
                print("  " + "-" * 70)
                for e in entries:
                    ts = str(e.processed_at.astimezone(timezone.utc))[:19] if e.processed_at else "?"
                    print(f"  {ts:22s}  {e.filename}")
            else:
                print("  (empty)")

    print()


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(
        description="Inspect and trigger the dream agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--base",
        default="http://localhost:8000/api",
        metavar="URL",
        help="API base URL (default: http://localhost:8000/api)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show unprocessed sessions and notes")

    run_p = sub.add_parser("run", help="Trigger dream processing")
    run_p.add_argument(
        "--direct",
        action="store_true",
        help="Run directly via DB (no server required)",
    )

    log_p = sub.add_parser("log", help="Show dream processing log")
    log_p.add_argument("--notes", action="store_true", help="Show notes log only")
    log_p.add_argument("--all", dest="show_all", action="store_true", help="Show both session and notes log")

    args = p.parse_args()

    if args.cmd == "status":
        asyncio.run(cmd_status())
    elif args.cmd == "run":
        asyncio.run(cmd_run(base_url=args.base, direct=args.direct))
    elif args.cmd == "log":
        show_sessions = not args.notes or args.show_all
        show_notes = args.notes or args.show_all
        asyncio.run(cmd_log(show_sessions=show_sessions, show_notes=show_notes))


if __name__ == "__main__":
    main()
