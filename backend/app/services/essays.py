"""Essay ownership and faculty-course authorization queries."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.course import CourseMemberRole, Enrollment
from app.db.models.essay import Essay
from app.db.models.user import User, UserRole


def list_accessible_essays(session: Session, *, user: User) -> list[Essay]:
    statement = select(Essay).order_by(Essay.created_at.desc())
    if user.role is UserRole.STUDENT:
        statement = statement.where(Essay.student_id == user.id)
    elif user.role is UserRole.FACULTY:
        statement = (
            statement.join(
                Enrollment,
                Enrollment.course_id == Essay.course_id,
            )
            .where(
                Enrollment.user_id == user.id,
                Enrollment.role == CourseMemberRole.FACULTY,
            )
            .distinct()
        )
    return list(session.scalars(statement))


def get_accessible_essay(
    session: Session,
    *,
    essay_id: UUID,
    user: User,
) -> Essay | None:
    essay = session.get(Essay, essay_id)
    if essay is None:
        return None
    if user.role is UserRole.ADMIN or (
        user.role is UserRole.STUDENT and essay.student_id == user.id
    ):
        return essay
    if user.role is UserRole.FACULTY and essay.course_id is not None:
        membership = session.scalar(
            select(Enrollment.id)
            .where(
                Enrollment.course_id == essay.course_id,
                Enrollment.user_id == user.id,
                Enrollment.role == CourseMemberRole.FACULTY,
            )
            .limit(1)
        )
        if membership is not None:
            return essay
    return None
