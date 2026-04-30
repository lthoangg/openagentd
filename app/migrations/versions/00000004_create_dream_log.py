"""create dream_log and dream_notes_log tables

Revision ID: 00000004
Revises: 00000003
Create Date: 2026-04-29

Domain: DreamLog + DreamNotesLog.  Tracks which sessions and note files
have been processed by the dream agent so it never re-processes them.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models.chat import TZDateTime

# revision identifiers, used by Alembic.
revision: str = "00000004"
down_revision: Union[str, Sequence[str], None] = "00000003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create dream_log and dream_notes_log tables."""
    op.create_table(
        "dream_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("processed_at", TZDateTime(timezone=True), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=True),
        sa.Column("topics_written", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    with op.batch_alter_table("dream_log", schema=None) as batch_op:
        batch_op.create_index("ix_dream_log_session_id", ["session_id"], unique=True)

    op.create_table(
        "dream_notes_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("processed_at", TZDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename"),
    )
    with op.batch_alter_table("dream_notes_log", schema=None) as batch_op:
        batch_op.create_index("ix_dream_notes_log_filename", ["filename"], unique=True)


def downgrade() -> None:
    """Drop dream_log and dream_notes_log tables."""
    with op.batch_alter_table("dream_notes_log", schema=None) as batch_op:
        batch_op.drop_index("ix_dream_notes_log_filename")
    op.drop_table("dream_notes_log")

    with op.batch_alter_table("dream_log", schema=None) as batch_op:
        batch_op.drop_index("ix_dream_log_session_id")
    op.drop_table("dream_log")
