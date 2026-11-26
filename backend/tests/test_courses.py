from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.security import create_access_token
from app.db.models.course import Course
from app.db.models.user import User, UserRole
from app.services.auth import create_user


def _token(user_id: UUID, settings: Settings) -> str:
    return create_access_token(
        user_id,
        settings.jwt_secret_key.get_secret_value(),
        settings.jwt_access_token_expire_minutes,
    )


def _create_user(
    session_factory: sessionmaker,
    *,
    email: str,
    role: UserRole,
) -> User:
    with session_factory() as session:
        return create_user(
            session,
            email=email,
            password="correct horse battery staple",
            full_name=email.split("@", 1)[0],
            role=role,
        )


@pytest.mark.asyncio
async def test_student_can_discover_enroll_and_upload_to_active_course(
    client: AsyncClient,
    test_session_factory: sessionmaker,
    test_settings: Settings,
) -> None:
    faculty = _create_user(
        test_session_factory,
        email="courses-faculty@example.com",
        role=UserRole.FACULTY,
    )
    student = _create_user(
        test_session_factory,
        email="courses-student@example.com",
        role=UserRole.STUDENT,
    )
    faculty_headers = {"Authorization": f"Bearer {_token(faculty.id, test_settings)}"}
    student_headers = {"Authorization": f"Bearer {_token(student.id, test_settings)}"}

    created = await client.post(
        "/api/v1/courses",
        json={"name": "Writing 101", "code": "write-101"},
        headers=faculty_headers,
    )
    assert created.status_code == 201
    course = created.json()

    available = await client.get("/api/v1/courses/available", headers=student_headers)
    assert available.status_code == 200
    assert len(available.json()) == 1
    assert available.json()[0]["id"] == course["id"]
    assert available.json()[0]["faculty_name"] == "courses-faculty"

    enrollment = await client.post(
        f"/api/v1/courses/{course['id']}/self-enrollment",
        json={"role": "faculty"},
        headers=student_headers,
    )
    assert enrollment.status_code == 201
    assert enrollment.json()["user_id"] == str(student.id)
    assert enrollment.json()["role"] == "student"

    enrolled_courses = await client.get("/api/v1/courses", headers=student_headers)
    assert [item["id"] for item in enrolled_courses.json()] == [course["id"]]
    available_after_enrollment = await client.get(
        "/api/v1/courses/available",
        headers=student_headers,
    )
    assert available_after_enrollment.json() == []

    duplicate = await client.post(
        f"/api/v1/courses/{course['id']}/self-enrollment",
        headers=student_headers,
    )
    assert duplicate.status_code == 409

    upload = await client.post(
        "/api/v1/essays",
        data={"course_id": course["id"]},
        files={"file": ("essay.txt", b"An enrolled student essay.", "text/plain")},
        headers=student_headers,
    )
    assert upload.status_code == 201
    assert upload.json()["course_id"] == course["id"]

    inactive_course = Course(
        id=uuid4(),
        name="Archived Writing",
        code="ARCHIVED",
        created_by_id=faculty.id,
        is_active=False,
    )
    with test_session_factory() as session:
        session.add(inactive_course)
        session.commit()

    unavailable_enrollment = await client.post(
        f"/api/v1/courses/{inactive_course.id}/self-enrollment",
        headers=student_headers,
    )
    assert unavailable_enrollment.status_code == 404


@pytest.mark.asyncio
async def test_course_enrollment_requires_student_and_preserves_faculty_controls(
    client: AsyncClient,
    test_session_factory: sessionmaker,
    test_settings: Settings,
) -> None:
    faculty = _create_user(
        test_session_factory,
        email="controls-faculty@example.com",
        role=UserRole.FACULTY,
    )
    student = _create_user(
        test_session_factory,
        email="controls-student@example.com",
        role=UserRole.STUDENT,
    )
    faculty_headers = {"Authorization": f"Bearer {_token(faculty.id, test_settings)}"}
    student_headers = {"Authorization": f"Bearer {_token(student.id, test_settings)}"}

    created = await client.post(
        "/api/v1/courses",
        json={"name": "Writing 102", "code": "write-102"},
        headers=faculty_headers,
    )
    course_id = created.json()["id"]

    unauthenticated = await client.get("/api/v1/courses/available")
    assert unauthenticated.status_code == 401

    faculty_discovery = await client.get(
        "/api/v1/courses/available",
        headers=faculty_headers,
    )
    assert faculty_discovery.status_code == 403

    faculty_self_enrollment = await client.post(
        f"/api/v1/courses/{course_id}/self-enrollment",
        headers=faculty_headers,
    )
    assert faculty_self_enrollment.status_code == 403

    student_cannot_enroll_another_user = await client.post(
        f"/api/v1/courses/{course_id}/enrollments",
        json={"user_id": str(student.id), "role": "student"},
        headers=student_headers,
    )
    assert student_cannot_enroll_another_user.status_code == 403

    faculty_enrollment = await client.post(
        f"/api/v1/courses/{course_id}/enrollments",
        json={"user_id": str(student.id), "role": "student"},
        headers=faculty_headers,
    )
    assert faculty_enrollment.status_code == 201

