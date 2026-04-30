"""Print a chronological timeline of all messages across a team session.

Shows timestamps, agent, role, and message detail so you can trace the
exact order of tool calls, inbox deliveries, and responses.

Usage:
  uv run python -m manual.team_timeline SESSION_ID
  uv run python -m manual.team_timeline SESSION_ID --full   # no content truncation
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.chat import ChatSession, SessionMessage


def _db_url() -> str:
    """Resolve the DB URL from settings.

    Uses ``settings.DATABASE_URL`` so the script follows the same XDG-based
    layout as the running server (``OPENAGENTD_DATA_DIR/openagentd.db``).
    """
    return settings.DATABASE_URL.get_secret_value()


async def run(session_id: str, *, full: bool = False) -> None:
    engine = create_async_engine(_db_url())
    trunc = None if full else 100
    sid = UUID(session_id)

    async with AsyncSession(engine) as s:
        # Resolve lead + all sub-sessions
        result = await s.exec(
            select(ChatSession).where(
                (ChatSession.id == sid) | (ChatSession.parent_session_id == sid)
            )
        )
        sessions = result.all()
        if not sessions:
            print(f"No session found: {session_id}")
            return

        sid_to_agent: dict[str, str] = {}
        for sess in sessions:
            label = sess.agent_name or "unknown"
            sid_to_agent[sess.id] = label
            role_tag = "[lead]" if sess.id == sid else "[member]"
            print(f"  {sess.id}  {label} {role_tag}")

        # Fetch all messages ordered by created_at
        all_sids = list(sid_to_agent.keys())
        result2 = await s.exec(
            select(SessionMessage)
            .where(SessionMessage.session_id.in_(all_sids))
            .order_by(SessionMessage.created_at)
        )
        msgs = result2.all()

    print(f"\n{'timestamp':26s}  {'agent':16s}  {'role':8s}  detail")
    print("-" * 110)

    for m in msgs:
        agent = sid_to_agent.get(m.session_id, "?")
        ts = str(m.created_at)[:23] if m.created_at else "?"

        if m.tool_calls:
            for tc in m.tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "?")
                args = fn.get("arguments") or ""
                if trunc:
                    args = args[:trunc]
                print(f"{ts:26s}  {agent:16s}  [asst  ]  CALL {name}({args})")

        elif m.tool_call_id:
            content = m.content or ""
            if trunc:
                content = content[:trunc]
            print(f"{ts:26s}  {agent:16s}  [tool  ]  RESULT {content}")

        else:
            content = m.content or ""
            if trunc:
                content = content[:trunc]
            extra = m.extra or {}
            from_agents = extra.get("from_agents") or (
                [extra["from_agent"]] if extra.get("from_agent") else []
            )
            tag = f" [inbox from={','.join(from_agents)}]" if from_agents else ""
            sum_tag = " [SUMMARY]" if m.is_summary else ""
            ctx_tag = " [excl]" if m.exclude_from_context else ""
            print(
                f"{ts:26s}  {agent:16s}  [{m.role:6s}]{tag}{sum_tag}{ctx_tag}  {content}"
            )

    print(f"\n{len(msgs)} messages total")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Timeline of all messages in a team session"
    )
    p.add_argument("session_id", help="Lead session ID")
    p.add_argument("--full", action="store_true", help="Don't truncate message content")
    args = p.parse_args()
    asyncio.run(run(args.session_id, full=args.full))


if __name__ == "__main__":
    main()
