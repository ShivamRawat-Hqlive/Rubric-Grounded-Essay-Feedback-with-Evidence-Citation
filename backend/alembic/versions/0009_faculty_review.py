"""Add faculty review fields and action history."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009_faculty_review"
down_revision: Union[str, None] = "0008_evidence_citations_mock"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

review_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "criterion_scores",
        sa.Column("faculty_strengths", review_json, nullable=True),
    )
    op.add_column(
        "criterion_scores",
        sa.Column("faculty_weaknesses", review_json, nullable=True),
    )
    op.add_column(
        "criterion_scores",
        sa.Column("faculty_suggestions", review_json, nullable=True),
    )
    op.create_table(
        "evaluation_review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("faculty_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_score_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('note_added', 'criterion_updated', 'approved', "
            "'rejected', 'changes_requested')",
            name="ck_evaluation_review_events_action",
        ),
        sa.ForeignKeyConstraint(
            ["criterion_score_id"],
            ["criterion_scores.id"],
            name="fk_evaluation_review_events_score",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
            name="fk_evaluation_review_events_evaluation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["faculty_id"],
            ["users.id"],
            name="fk_evaluation_review_events_faculty",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_review_events"),
    )
    op.create_index(
        "ix_evaluation_review_events_evaluation_created",
        "evaluation_review_events",
        ["evaluation_id", "created_at"],
    )
    op.create_index(
        "ix_evaluation_review_events_faculty_id",
        "evaluation_review_events",
        ["faculty_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_review_events_faculty_id",
        table_name="evaluation_review_events",
    )
    op.drop_index(
        "ix_evaluation_review_events_evaluation_created",
        table_name="evaluation_review_events",
    )
    op.drop_table("evaluation_review_events")
    op.drop_column("criterion_scores", "faculty_suggestions")
    op.drop_column("criterion_scores", "faculty_weaknesses")
    op.drop_column("criterion_scores", "faculty_strengths")
