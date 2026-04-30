"""create scheduled_task table

Revision ID: 00000003
Revises: 00000002
Create Date: 2026-04-27

Domain: ScheduledTask.  Captures the scheduler table in its final shape.
Independent of ``chat_sessions`` (no FK) — the scheduler stores the
session id as an opaque string after the run completes.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models.chat import TZDateTime

# revision identifiers, used by Alembic.
revision: str = "00000003"
down_revision: Union[str, Sequence[str], None] = "00000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create scheduled_task table."""
    op.create_table(
        "scheduled_task",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("agent", sa.String(length=100), nullable=False),
        sa.Column("schedule_type", sa.String(length=20), nullable=False),
        sa.Column("at_datetime", TZDateTime(timezone=True), nullable=True),
        sa.Column("every_seconds", sa.Integer(), nullable=True),
        sa.Column("cron_expression", sa.String(length=100), nullable=True),
        sa.Column(
            "timezone", sa.String(length=50), nullable=False, server_default="UTC"
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("session_id", sa.String(length=200), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", TZDateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_fire_at", TZDateTime(timezone=True), nullable=True),
        sa.Column("created_at", TZDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", TZDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("scheduled_task", schema=None) as batch_op:
        batch_op.create_index("ix_scheduled_task_name", ["name"], unique=True)
        batch_op.create_index("ix_scheduled_task_enabled", ["enabled"], unique=False)


def downgrade() -> None:
    """Drop scheduled_task table."""
    with op.batch_alter_table("scheduled_task", schema=None) as batch_op:
        batch_op.drop_index("ix_scheduled_task_enabled")
        batch_op.drop_index("ix_scheduled_task_name")
    op.drop_table("scheduled_task")
