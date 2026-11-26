"""Minimal course membership model for essay access control."""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CourseMemberRole(str, Enum):
    STUDENT = "student"
    FACULTY = "faculty"


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("code", name="uq_courses_code"),
        CheckConstraint("length(trim(name)) > 0", name="ck_courses_name_nonempty"),
        CheckConstraint("length(trim(code)) > 0", name="ck_courses_code_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "user_id", name="uq_enrollments_course_user"),
        CheckConstraint(
            "role IN ('student', 'faculty')",
            name="ck_enrollments_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    course_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[CourseMemberRole] = mapped_column(
        SqlEnum(
            CourseMemberRole,
            name="course_member_role",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum_type: [role.value for role in enum_type],
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
