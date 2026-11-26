"""Persisted AI evaluations and independent faculty score fields."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

EVALUATION_JSON = JSON().with_variant(JSONB(), "postgresql")


class EvaluationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    FAILED = "failed"


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "rubric_version_id",
            name="uq_evaluations_id_rubric_version",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'needs_review', 'approved', "
            "'rejected', 'changes_requested', 'failed')",
            name="ck_evaluations_status",
        ),
        CheckConstraint(
            "evaluation_mode IN ('openai', 'mock')",
            name="ck_evaluations_mode",
        ),
        Index(
            "uq_evaluations_inflight_essay_rubric",
            "essay_id",
            "rubric_version_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_evaluations_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    essay_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("essays.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rubric_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    requested_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[EvaluationStatus] = mapped_column(
        SqlEnum(
            EvaluationStatus,
            name="evaluation_status",
            native_enum=False,
            create_constraint=False,
            length=24,
            values_callable=lambda enum_type: [status.value for status in enum_type],
        ),
        nullable=False,
        default=EvaluationStatus.RUNNING,
    )
    evaluation_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="openai",
        server_default="openai",
    )
    ai_total_score: Mapped[Decimal | None] = mapped_column(Numeric(19, 10))
    faculty_total_score: Mapped[Decimal | None] = mapped_column(Numeric(19, 10))
    has_unsupported_flags: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CriterionScore(Base):
    __tablename__ = "criterion_scores"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id",
            "criterion_id",
            name="uq_criterion_scores_eval_criterion",
        ),
        ForeignKeyConstraint(
            ["evaluation_id", "rubric_version_id"],
            ["evaluations.id", "evaluations.rubric_version_id"],
            name="fk_criterion_scores_evaluation_version",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["rubric_version_id", "criterion_id"],
            ["rubric_criteria.rubric_version_id", "rubric_criteria.id"],
            name="fk_criterion_scores_version_criterion",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    evaluation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rubric_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    criterion_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ai_score: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    ai_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(EVALUATION_JSON, nullable=False)
    weaknesses: Mapped[list[str]] = mapped_column(EVALUATION_JSON, nullable=False)
    suggestions: Mapped[list[str]] = mapped_column(EVALUATION_JSON, nullable=False)
    claims: Mapped[list[dict[str, object]]] = mapped_column(
        "claims_json",
        EVALUATION_JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    faculty_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    faculty_rationale: Mapped[str | None] = mapped_column(Text)
    faculty_strengths: Mapped[list[str] | None] = mapped_column(EVALUATION_JSON)
    faculty_weaknesses: Mapped[list[str] | None] = mapped_column(EVALUATION_JSON)
    faculty_suggestions: Mapped[list[str] | None] = mapped_column(EVALUATION_JSON)


class EvaluationReviewEvent(Base):
    __tablename__ = "evaluation_review_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('note_added', 'criterion_updated', 'approved', "
            "'rejected', 'changes_requested')",
            name="ck_evaluation_review_events_action",
        ),
        Index(
            "ix_evaluation_review_events_evaluation_created",
            "evaluation_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    evaluation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    faculty_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    criterion_score_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("criterion_scores.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
