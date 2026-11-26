"""Rubric course-scope and ownership authorization queries."""

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db.models.course import Course, CourseMemberRole, Enrollment
from app.db.models.rubric import Rubric, RubricStatus, RubricVersion
from app.db.models.user import User, UserRole


def _published_version_exists():
    return exists(
        select(RubricVersion.id).where(
            RubricVersion.rubric_id == Rubric.id,
            RubricVersion.is_published.is_(True),
        )
    )


def rubric_has_published_version(session: Session, *, rubric_id: UUID) -> bool:
    return (
        session.scalar(
            select(RubricVersion.id)
            .where(
                RubricVersion.rubric_id == rubric_id,
                RubricVersion.is_published.is_(True),
            )
            .limit(1)
        )
        is not None
    )


def list_accessible_rubrics(session: Session, *, user: User) -> list[Rubric]:
    statement = select(Rubric).order_by(Rubric.created_at.desc())
    if user.role is UserRole.FACULTY:
        statement = (
            statement.join(Course, Course.id == Rubric.course_id)
            .join(Enrollment, Enrollment.course_id == Rubric.course_id)
            .where(
                Course.is_active.is_(True),
                Enrollment.user_id == user.id,
                Enrollment.role == CourseMemberRole.FACULTY,
            )
            .distinct()
        )
    elif user.role is UserRole.STUDENT:
        statement = (
            statement.join(Course, Course.id == Rubric.course_id)
            .join(Enrollment, Enrollment.course_id == Rubric.course_id)
            .where(
                Course.is_active.is_(True),
                Enrollment.user_id == user.id,
                Enrollment.role == CourseMemberRole.STUDENT,
                Rubric.status == RubricStatus.PUBLISHED,
                _published_version_exists(),
            )
            .distinct()
        )
    return list(session.scalars(statement))


def get_accessible_rubric(
    session: Session,
    *,
    rubric_id: UUID,
    user: User,
) -> Rubric | None:
    rubric = session.get(Rubric, rubric_id)
    if rubric is None:
        return None
    if user.role is UserRole.ADMIN:
        return rubric

    course = session.get(Course, rubric.course_id)
    if course is None or not course.is_active:
        return None
    if user.role is UserRole.FACULTY:
        role = CourseMemberRole.FACULTY
    elif user.role is UserRole.STUDENT:
        if (
            rubric.status is not RubricStatus.PUBLISHED
            or not rubric_has_published_version(session, rubric_id=rubric.id)
        ):
            return None
        role = CourseMemberRole.STUDENT
    else:
        return None

    membership = session.scalar(
        select(Enrollment.id)
        .where(
            Enrollment.course_id == rubric.course_id,
            Enrollment.user_id == user.id,
            Enrollment.role == role,
        )
        .limit(1)
    )
    if membership is None:
        return None
    return rubric


def get_accessible_rubric_versions(
    session: Session,
    *,
    rubric: Rubric,
    user: User,
) -> list[RubricVersion]:
    statement = (
        select(RubricVersion)
        .where(RubricVersion.rubric_id == rubric.id)
        .order_by(RubricVersion.version_number)
    )
    if user.role is UserRole.STUDENT:
        statement = statement.where(RubricVersion.is_published.is_(True))
    return list(session.scalars(statement))


def get_accessible_rubric_version(
    session: Session,
    *,
    version_id: UUID,
    user: User,
) -> tuple[Rubric, RubricVersion] | None:
    version = session.get(RubricVersion, version_id)
    if version is None:
        return None
    rubric = get_accessible_rubric(
        session,
        rubric_id=version.rubric_id,
        user=user,
    )
    if rubric is None:
        return None
    if user.role is UserRole.STUDENT and not version.is_published:
        return None
    return rubric, version


def get_owned_rubric(
    session: Session,
    *,
    rubric_id: UUID,
    user: User,
    lock: bool = False,
) -> Rubric | None:
    if user.role is not UserRole.FACULTY:
        return None
    statement = select(Rubric).where(
        Rubric.id == rubric_id,
        Rubric.created_by_id == user.id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    rubric = session.scalar(statement)
    if rubric is None:
        return None
    course = session.get(Course, rubric.course_id)
    if course is None or not course.is_active:
        return None
    membership = session.scalar(
        select(Enrollment.id)
        .where(
            Enrollment.course_id == rubric.course_id,
            Enrollment.user_id == user.id,
            Enrollment.role == CourseMemberRole.FACULTY,
        )
        .limit(1)
    )
    return rubric if membership is not None else None


def get_owned_rubric_version(
    session: Session,
    *,
    version_id: UUID,
    user: User,
    lock: bool = False,
) -> tuple[Rubric, RubricVersion] | None:
    rubric_id = session.scalar(
        select(RubricVersion.rubric_id).where(RubricVersion.id == version_id)
    )
    if rubric_id is None:
        return None
    rubric = get_owned_rubric(
        session,
        rubric_id=rubric_id,
        user=user,
        lock=lock,
    )
    if rubric is None:
        return None
    if lock:
        version = session.scalar(
            select(RubricVersion)
            .where(RubricVersion.id == version_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        version = session.get(RubricVersion, version_id)
    return (rubric, version) if version is not None else None
