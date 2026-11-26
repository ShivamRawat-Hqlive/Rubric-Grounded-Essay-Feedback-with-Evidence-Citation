"""Course-scoped rubrics and immutable published versions."""

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
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RUBRIC_JSON = JSON().with_variant(JSONB(), "postgresql")


class RubricStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Rubric(Base):
    __tablename__ = "rubrics"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_rubrics_status",
        ),
        CheckConstraint("length(trim(title)) > 0", name="ck_rubrics_title_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    course_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("courses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RubricStatus] = mapped_column(
        SqlEnum(
            RubricStatus,
            name="rubric_status",
            native_enum=False,
            create_constraint=False,
            length=16,
            values_callable=lambda enum_type: [status.value for status in enum_type],
        ),
        nullable=False,
        default=RubricStatus.DRAFT,
        server_default=RubricStatus.DRAFT.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RubricVersion(Base):
    __tablename__ = "rubric_versions"
    __table_args__ = (
        UniqueConstraint("rubric_id", "version_number", name="uq_rubric_versions_number"),
        CheckConstraint("version_number > 0", name="ck_rubric_versions_number_positive"),
        CheckConstraint(
            "(is_published = false AND published_at IS NULL) OR "
            "(is_published = true AND published_at IS NOT NULL AND snapshot IS NOT NULL)",
            name="ck_rubric_versions_publish_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    rubric_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("rubrics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, object] | None] = mapped_column(RUBRIC_JSON)


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (
        UniqueConstraint(
            "rubric_version_id",
            "id",
            name="uq_rubric_criteria_version_id",
        ),
        UniqueConstraint(
            "rubric_version_id",
            "sort_order",
            name="uq_rubric_criteria_sort_order",
        ),
        CheckConstraint(
            "min_score < max_score",
            name="ck_rubric_criteria_score_range",
        ),
        CheckConstraint(
            "weight > 0 AND weight <= 1",
            name="ck_rubric_criteria_weight_range",
        ),
        CheckConstraint("sort_order >= 0", name="ck_rubric_criteria_sort_order"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    rubric_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    levels_json: Mapped[list[dict[str, str]]] = mapped_column(
        RUBRIC_JSON, nullable=False, default=list
    )
    max_score: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    min_score: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
