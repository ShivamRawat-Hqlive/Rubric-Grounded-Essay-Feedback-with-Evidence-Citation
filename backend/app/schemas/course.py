"""Course and enrollment API schemas."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.course import CourseMemberRole


class CourseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=32)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}", value):
            raise ValueError("Course code contains invalid characters.")
        return value.upper()


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str
    created_by_id: UUID
    is_active: bool
    created_at: datetime


class AvailableCourseResponse(CourseResponse):
    faculty_name: str | None = None


class EnrollmentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: CourseMemberRole


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    user_id: UUID
    role: CourseMemberRole
    created_at: datetime
