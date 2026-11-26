"""Add course-scoped rubric versioning and criteria.

Revision ID: 0005_rubric_management
Revises: 0004_essay_upload_and_courses
Create Date: 2026-11-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_rubric_management"
down_revision: Union[str, None] = "0004_essay_upload_and_courses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

rubric_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "rubrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_rubrics_status",
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_rubrics_title_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name="fk_rubrics_course_id_courses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_rubrics_created_by_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rubrics_course_id", "rubrics", ["course_id"])
    op.create_index("ix_rubrics_created_by_id", "rubrics", ["created_by_id"])

    op.create_table(
        "rubric_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rubric_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "is_published",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot", rubric_json, nullable=True),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_rubric_versions_number_positive",
        ),
        sa.CheckConstraint(
            "(is_published = false AND published_at IS NULL) OR "
            "(is_published = true AND published_at IS NOT NULL AND snapshot IS NOT NULL)",
            name="ck_rubric_versions_publish_state",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_id"],
            ["rubrics.id"],
            name="fk_rubric_versions_rubric_id_rubrics",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rubric_id",
            "version_number",
            name="uq_rubric_versions_number",
        ),
    )
    op.create_index(
        "ix_rubric_versions_rubric_id",
        "rubric_versions",
        ["rubric_id"],
    )

    op.create_table(
        "rubric_criteria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("levels_json", rubric_json, nullable=False),
        sa.Column("max_score", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("min_score", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("weight", sa.Numeric(precision=7, scale=6), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "min_score < max_score",
            name="ck_rubric_criteria_score_range",
        ),
        sa.CheckConstraint(
            "weight > 0 AND weight <= 1",
            name="ck_rubric_criteria_weight_range",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_rubric_criteria_sort_order",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_version_id"],
            ["rubric_versions.id"],
            name="fk_rubric_criteria_rubric_version_id_rubric_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rubric_version_id",
            "sort_order",
            name="uq_rubric_criteria_sort_order",
        ),
    )
    op.create_index(
        "ix_rubric_criteria_rubric_version_id",
        "rubric_criteria",
        ["rubric_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rubric_criteria_rubric_version_id",
        table_name="rubric_criteria",
    )
    op.drop_table("rubric_criteria")
    op.drop_index("ix_rubric_versions_rubric_id", table_name="rubric_versions")
    op.drop_table("rubric_versions")
    op.drop_index("ix_rubrics_created_by_id", table_name="rubrics")
    op.drop_index("ix_rubrics_course_id", table_name="rubrics")
    op.drop_table("rubrics")
