"""Add minimal course membership and essay document storage.

Revision ID: 0004_essay_upload_and_courses
Revises: 0003_refresh_session_families
Create Date: 2026-11-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_essay_upload_and_courses"
down_revision: Union[str, None] = "0003_refresh_session_families"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


document_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_courses_name_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(code)) > 0",
            name="ck_courses_code_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_courses_created_by_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_courses_code"),
    )
    op.create_index("ix_courses_created_by_id", "courses", ["created_by_id"])

    op.create_table(
        "enrollments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=7), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('student', 'faculty')",
            name="ck_enrollments_role",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name="fk_enrollments_course_id_courses",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_enrollments_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "course_id",
            "user_id",
            name="uq_enrollments_course_user",
        ),
    )
    op.create_index("ix_enrollments_course_id", "enrollments", ["course_id"])
    op.create_index("ix_enrollments_user_id", "enrollments", ["user_id"])

    op.create_table(
        "essays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("parse_status", sa.String(length=16), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("normalizer_version", sa.String(length=32), nullable=False),
        sa.Column("offset_alignment", document_json, nullable=False),
        sa.Column("page_map", document_json, nullable=False),
        sa.Column("extractor_name", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "parse_status IN ('parsed', 'failed')",
            name="ck_essays_parse_status",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_essays_size_positive"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_essays_sha256_length"),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name="fk_essays_course_id_courses",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name="fk_essays_student_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_path", name="uq_essays_stored_path"),
    )
    op.create_index("ix_essays_student_id", "essays", ["student_id"])
    op.create_index("ix_essays_course_id", "essays", ["course_id"])

    op.create_table(
        "essay_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("essay_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("sentence_index", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("extracted_char_start", sa.Integer(), nullable=False),
        sa.Column("extracted_char_end", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="ck_essay_chunks_index_nonnegative",
        ),
        sa.CheckConstraint(
            "sentence_index >= 0",
            name="ck_essay_chunks_sentence_nonnegative",
        ),
        sa.CheckConstraint(
            "char_start >= 0 AND char_end > char_start",
            name="ck_essay_chunks_normalized_offsets",
        ),
        sa.CheckConstraint(
            "extracted_char_start >= 0 AND extracted_char_end > extracted_char_start",
            name="ck_essay_chunks_extracted_offsets",
        ),
        sa.ForeignKeyConstraint(
            ["essay_id"],
            ["essays.id"],
            name="fk_essay_chunks_essay_id_essays",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "essay_id",
            "chunk_index",
            name="uq_essay_chunks_index",
        ),
    )
    op.create_index("ix_essay_chunks_essay_id", "essay_chunks", ["essay_id"])


def downgrade() -> None:
    op.drop_index("ix_essay_chunks_essay_id", table_name="essay_chunks")
    op.drop_table("essay_chunks")
    op.drop_index("ix_essays_course_id", table_name="essays")
    op.drop_index("ix_essays_student_id", table_name="essays")
    op.drop_table("essays")
    op.drop_index("ix_enrollments_user_id", table_name="enrollments")
    op.drop_index("ix_enrollments_course_id", table_name="enrollments")
    op.drop_table("enrollments")
    op.drop_index("ix_courses_created_by_id", table_name="courses")
    op.drop_table("courses")
