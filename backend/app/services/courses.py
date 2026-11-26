"""Course membership queries used to scope faculty access."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.course import Course, CourseMemberRole, Enrollment
from app.db.models.user import User


def has_course_membership(
    session: Session,
    *,
    user: User,
    course_id: UUID,
    role: CourseMemberRole | None = None,
) -> bool:
    statement = select(Enrollment.id).where(
        Enrollment.user_id == user.id,
        Enrollment.course_id == course_id,
    )
    if role is not None:
        statement = statement.where(Enrollment.role == role)
    return session.scalar(statement.limit(1)) is not None


def can_manage_course(session: Session, *, user: User, course: Course) -> bool:
    return user.role.value == "admin" or (
        user.role.value == "faculty" and course.created_by_id == user.id
    )
