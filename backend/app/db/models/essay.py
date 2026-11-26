"""Essay and parsed sentence storage."""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EssayParseStatus(str, Enum):
    PARSED = "parsed"
    FAILED = "failed"


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Essay(Base):
    __tablename__ = "essays"
    __table_args__ = (
        CheckConstraint(
            "parse_status IN ('parsed', 'failed')",
            name="ck_essays_parse_status",
        ),
        CheckConstraint("size_bytes > 0", name="ck_essays_size_positive"),
        CheckConstraint("length(sha256) = 64", name="ck_essays_sha256_length"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    course_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("courses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    parse_status: Mapped[EssayParseStatus] = mapped_column(
        SqlEnum(
            EssayParseStatus,
            name="essay_parse_status",
            native_enum=False,
            create_constraint=False,
            length=16,
            values_callable=lambda enum_type: [status.value for status in enum_type],
        ),
        nullable=False,
        default=EssayParseStatus.PARSED,
    )
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    offset_alignment: Mapped[list[list[int]]] = mapped_column(
        JSON_DOCUMENT, nullable=False
    )
    page_map: Mapped[list[dict[str, int | None]]] = mapped_column(
        JSON_DOCUMENT, nullable=False
    )
    extractor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EssayChunk(Base):
    __tablename__ = "essay_chunks"
    __table_args__ = (
        UniqueConstraint("essay_id", "chunk_index", name="uq_essay_chunks_index"),
        CheckConstraint("chunk_index >= 0", name="ck_essay_chunks_index_nonnegative"),
        CheckConstraint("sentence_index >= 0", name="ck_essay_chunks_sentence_nonnegative"),
        CheckConstraint("char_start >= 0 AND char_end > char_start", name="ck_essay_chunks_normalized_offsets"),
        CheckConstraint(
            "extracted_char_start >= 0 AND extracted_char_end > extracted_char_start",
            name="ck_essay_chunks_extracted_offsets",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    essay_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("essays.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
