"""Allow evaluation scores to use the rubric's complete configured range.

Revision ID: 0007_signed_evaluation_scores
Revises: 0006_ai_evaluations
Create Date: 2026-12-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007_signed_evaluation_scores"
down_revision: Union[str, None] = "0006_ai_evaluations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_evaluations_ai_total_nonnegative",
        "evaluations",
        type_="check",
    )
    op.drop_constraint(
        "ck_criterion_scores_ai_nonnegative",
        "criterion_scores",
        type_="check",
    )
    op.drop_constraint(
        "ck_criterion_scores_faculty_nonnegative",
        "criterion_scores",
        type_="check",
    )


def downgrade() -> None:
    op.create_check_constraint(
        "ck_evaluations_ai_total_nonnegative",
        "evaluations",
        "ai_total_score IS NULL OR ai_total_score >= 0",
    )
    op.create_check_constraint(
        "ck_criterion_scores_ai_nonnegative",
        "criterion_scores",
        "ai_score >= 0",
    )
    op.create_check_constraint(
        "ck_criterion_scores_faculty_nonnegative",
        "criterion_scores",
        "faculty_score IS NULL OR faculty_score >= 0",
    )
