"""create chat_sessions table

Revision ID: 00000001
Revises:
Create Date: 2026-04-27

Domain: ChatSession.  Captures the table in its final shape — a single
top-level session row keyed by UUIDv7 with an optional self-referential
``parent_session_id`` for team-member sessions and an optional
``scheduled_task_name`` for sessions created by the scheduler.

The legacy ``session_type`` column is intentionally absent: top-level
sessions are identified by ``parent_session_id IS NULL``, no enum needed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models.chat import TZDateTime

# revision identifiers, used by Alembic.
revision: str = "00000001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create chat_sessions table."""
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_session_id", sa.Uuid(), nullable=True),
        sa.Column("agent_name", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("scheduled_task_name", sa.String(length=100), nullable=True),
        sa.Column("created_at", TZDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", TZDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_session_id"], ["chat_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_sessions_parent_session_id"),
            ["parent_session_id"],
            unique=False,
        )


def downgrade() -> None:
    """Drop chat_sessions table."""
    with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_sessions_parent_session_id"))
    op.drop_table("chat_sessions")
