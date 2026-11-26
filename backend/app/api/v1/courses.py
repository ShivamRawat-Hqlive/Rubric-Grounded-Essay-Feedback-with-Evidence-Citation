"""Minimal course membership API for essay authorization."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.models.course import Course, CourseMemberRole, Enrollment
from app.db.models.user import User, UserRole
from app.db.session import get_db
from app.schemas.course import (
    AvailableCourseResponse,
    CourseCreateRequest,
    CourseResponse,
    EnrollmentCreateRequest,
    EnrollmentResponse,
)
from app.services.courses import can_manage_course, has_course_membership

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post(
    "",
    response_model=CourseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_course(
    request: CourseCreateRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY, UserRole.ADMIN)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> Course:
    course = Course(
        id=uuid4(),
        name=request.name,
        code=request.code,
        created_by_id=current_user.id,
    )
    session.add(course)
    if current_user.role is UserRole.FACULTY:
        session.add(
            Enrollment(
                course_id=course.id,
                user_id=current_user.id,
                role=CourseMemberRole.FACULTY,
            )
        )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A course with this code already exists.",
        ) from exc
    session.refresh(course)
    return course


@router.get("", response_model=list[CourseResponse])
def list_courses(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> list[Course]:
    statement = select(Course).where(Course.is_active.is_(True))
    if current_user.role is not UserRole.ADMIN:
        statement = (
            statement.join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.user_id == current_user.id)
            .distinct()
        )
    return list(session.scalars(statement.order_by(Course.name)))


@router.get("/available", response_model=list[AvailableCourseResponse])
def list_available_courses(
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.STUDENT)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> list[AvailableCourseResponse]:
    existing_enrollment = select(Enrollment.id).where(
        Enrollment.course_id == Course.id,
        Enrollment.user_id == current_user.id,
    )
    statement = (
        select(Course, User.full_name, User.role)
        .join(User, User.id == Course.created_by_id)
        .where(Course.is_active.is_(True), ~existing_enrollment.exists())
        .order_by(Course.name)
    )
    return [
        AvailableCourseResponse.model_validate(course).model_copy(
            update={
                "faculty_name": (
                    faculty_name if creator_role is UserRole.FACULTY else None
                )
            }
        )
        for course, faculty_name, creator_role in session.execute(statement)
    ]


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> Course:
    course = session.get(Course, course_id)
    if course is None or (
        current_user.role is not UserRole.ADMIN
        and not has_course_membership(
            session,
            user=current_user,
            course_id=course_id,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found.",
        )
    return course


@router.post(
    "/{course_id}/enrollments",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def enroll_user(
    course_id: UUID,
    request: EnrollmentCreateRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY, UserRole.ADMIN)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> Enrollment:
    course = session.get(Course, course_id)
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found.",
        )
    if not can_manage_course(session, user=current_user, course=course):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found.",
        )
    if (
        current_user.role is UserRole.FACULTY
        and request.role is not CourseMemberRole.STUDENT
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faculty may enroll students only.",
        )

    user = session.get(User, request.user_id)
    expected_user_role = UserRole(request.role.value)
    if user is None or not user.is_active or user.role is not expected_user_role:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The requested user role is not eligible for this enrollment.",
        )

    enrollment = Enrollment(
        course_id=course_id,
        user_id=user.id,
        role=request.role,
    )
    session.add(enrollment)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The user is already enrolled in this course.",
        ) from exc
    session.refresh(enrollment)
    return enrollment


@router.post(
    "/{course_id}/self-enrollment",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def enroll_current_student(
    course_id: UUID,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.STUDENT)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> Enrollment:
    course = session.get(Course, course_id)
    if course is None or not course.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found.",
        )

    existing_enrollment = select(Enrollment.id).where(
        Enrollment.course_id == course_id,
        Enrollment.user_id == current_user.id,
    )
    if session.scalar(existing_enrollment.limit(1)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already enrolled in this course.",
        )

    enrollment = Enrollment(
        course_id=course_id,
        user_id=current_user.id,
        role=CourseMemberRole.STUDENT,
    )
    session.add(enrollment)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already enrolled in this course.",
        ) from exc
    session.refresh(enrollment)
    return enrollment
