"""Persist evaluation mode and verified criterion evidence.

Revision ID: 0008_evidence_citations_mock
Revises: 0007_signed_evaluation_scores
Create Date: 2026-11-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_evidence_citations_mock"
down_revision: Union[str, None] = "0007_signed_evaluation_scores"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

evaluation_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "evaluations",
        sa.Column(
            "evaluation_mode",
            sa.String(length=16),
            server_default=sa.text("'openai'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_evaluations_mode",
        "evaluations",
        "evaluation_mode IN ('openai', 'mock')",
    )
    op.add_column(
        "criterion_scores",
        sa.Column(
            "claims_json",
            evaluation_json,
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("criterion_scores", "claims_json")
    op.drop_constraint("ck_evaluations_mode", "evaluations", type_="check")
    op.drop_column("evaluations", "evaluation_mode")
