"""Add persistent AI evaluation results.

Revision ID: 0006_ai_evaluations
Revises: 0005_rubric_management
Create Date: 2026-12-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_ai_evaluations"
down_revision: Union[str, None] = "0005_rubric_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

evaluation_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_rubric_criteria_version_id",
        "rubric_criteria",
        ["rubric_version_id", "id"],
    )

    op.create_table(
        "evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("essay_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("ai_total_score", sa.Numeric(precision=19, scale=10), nullable=True),
        sa.Column(
            "faculty_total_score",
            sa.Numeric(precision=19, scale=10),
            nullable=True,
        ),
        sa.Column(
            "has_unsupported_flags",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'needs_review', 'approved', "
            "'rejected', 'changes_requested', 'failed')",
            name="ck_evaluations_status",
        ),
        sa.CheckConstraint(
            "ai_total_score IS NULL OR ai_total_score >= 0",
            name="ck_evaluations_ai_total_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["essay_id"],
            ["essays.id"],
            name="fk_evaluations_essay_id_essays",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_version_id"],
            ["rubric_versions.id"],
            name="fk_evaluations_rubric_version_id_rubric_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name="fk_evaluations_requested_by_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "rubric_version_id",
            name="uq_evaluations_id_rubric_version",
        ),
    )
    op.create_index("ix_evaluations_essay_id", "evaluations", ["essay_id"])
    op.create_index(
        "ix_evaluations_rubric_version_id",
        "evaluations",
        ["rubric_version_id"],
    )
    op.create_index(
        "ix_evaluations_requested_by_id",
        "evaluations",
        ["requested_by_id"],
    )
    op.create_index("ix_evaluations_status", "evaluations", ["status"])
    op.create_index(
        "uq_evaluations_inflight_essay_rubric",
        "evaluations",
        ["essay_id", "rubric_version_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "criterion_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_id", sa.Uuid(), nullable=False),
        sa.Column("ai_score", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("ai_rationale", sa.Text(), nullable=False),
        sa.Column("strengths", evaluation_json, nullable=False),
        sa.Column("weaknesses", evaluation_json, nullable=False),
        sa.Column("suggestions", evaluation_json, nullable=False),
        sa.Column(
            "faculty_score",
            sa.Numeric(precision=12, scale=4),
            nullable=True,
        ),
        sa.Column("faculty_rationale", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "ai_score >= 0",
            name="ck_criterion_scores_ai_nonnegative",
        ),
        sa.CheckConstraint(
            "faculty_score IS NULL OR faculty_score >= 0",
            name="ck_criterion_scores_faculty_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id", "rubric_version_id"],
            ["evaluations.id", "evaluations.rubric_version_id"],
            name="fk_criterion_scores_evaluation_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_version_id", "criterion_id"],
            ["rubric_criteria.rubric_version_id", "rubric_criteria.id"],
            name="fk_criterion_scores_version_criterion",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluation_id",
            "criterion_id",
            name="uq_criterion_scores_eval_criterion",
        ),
    )


def downgrade() -> None:
    op.drop_table("criterion_scores")
    op.drop_index(
        "uq_evaluations_inflight_essay_rubric",
        table_name="evaluations",
    )
    op.drop_index("ix_evaluations_status", table_name="evaluations")
    op.drop_index("ix_evaluations_requested_by_id", table_name="evaluations")
    op.drop_index("ix_evaluations_rubric_version_id", table_name="evaluations")
    op.drop_index("ix_evaluations_essay_id", table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_constraint(
        "uq_rubric_criteria_version_id",
        "rubric_criteria",
        type_="unique",
    )
