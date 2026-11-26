"""Track refresh-token families for reuse revocation.

Revision ID: 0003_refresh_session_families
Revises: 0002_add_refresh_sessions
Create Date: 2026-11-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_refresh_session_families"
down_revision: Union[str, None] = "0002_add_refresh_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_sessions",
        sa.Column("family_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        sa.text("UPDATE refresh_sessions SET family_id = id WHERE family_id IS NULL")
    )
    op.alter_column(
        "refresh_sessions",
        "family_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.create_index(
        "ix_refresh_sessions_family_id",
        "refresh_sessions",
        ["family_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_sessions_family_id", table_name="refresh_sessions")
    op.drop_column("refresh_sessions", "family_id")
