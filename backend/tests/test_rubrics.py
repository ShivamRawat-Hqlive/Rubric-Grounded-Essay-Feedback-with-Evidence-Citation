"""Rubric authoring, course access, and publication workflow tests."""

from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.security import create_access_token
from app.db.models.course import Course, CourseMemberRole, Enrollment
from app.db.models.rubric import RubricStatus
from app.db.models.user import User, UserRole
from app.services.auth import create_user


def _create_user(
    session_factory: sessionmaker,
    *,
    email: str,
    role: UserRole,
) -> User:
    with session_factory() as session:
        user = create_user(
            session,
            email=email,
            password="correct horse battery staple",
            full_name=email.split("@", 1)[0],
            role=role,
        )
        return user


def _create_course(
    session_factory: sessionmaker,
    *,
    faculty: list[User],
    students: list[User],
) -> UUID:
    course_id = uuid4()
    with session_factory() as session:
        session.add(
            Course(
                id=course_id,
                name="Rubric Course",
                code="RUBRIC-101",
                created_by_id=faculty[0].id,
            )
        )
        session.add_all(
            [
                Enrollment(
                    course_id=course_id,
                    user_id=user.id,
                    role=CourseMemberRole.FACULTY,
                )
                for user in faculty
            ]
            + [
                Enrollment(
                    course_id=course_id,
                    user_id=user.id,
                    role=CourseMemberRole.STUDENT,
                )
                for user in students
            ]
        )
        session.commit()
    return course_id


def _headers(user: User, settings: Settings) -> dict[str, str]:
    token = create_access_token(
        user.id,
        settings.jwt_secret_key.get_secret_value(),
        settings.jwt_access_token_expire_minutes,
    )
    return {"Authorization": f"Bearer {token}"}


def _criteria(weights: tuple[str, str] = ("0.4", "0.6")) -> list[dict[str, object]]:
    return [
        {
            "name": "Analysis",
            "description": "Evaluates the quality of analysis.",
            "min_score": "0",
            "max_score": "4",
            "weight": weights[0],
            "sort_order": 0,
            "levels": [
                {"score": "0", "description": "No relevant analysis."},
                {"score": "4", "description": "Insightful and complete analysis."},
            ],
        },
        {
            "name": "Evidence",
            "description": "Evaluates relevant supporting evidence.",
            "min_score": "0",
            "max_score": "4",
            "weight": weights[1],
            "sort_order": 1,
        },
    ]


@pytest.mark.asyncio
async def test_rubric_draft_publish_version_archive_and_student_visibility(
    client: AsyncClient,
    test_session_factory: sessionmaker,
    test_settings: Settings,
) -> None:
    owner = _create_user(
        test_session_factory,
        email="rubric-owner@example.com",
        role=UserRole.FACULTY,
    )
    peer_faculty = _create_user(
        test_session_factory,
        email="rubric-peer@example.com",
        role=UserRole.FACULTY,
    )
    outsider_faculty = _create_user(
        test_session_factory,
        email="rubric-outsider@example.com",
        role=UserRole.FACULTY,
    )
    student = _create_user(
        test_session_factory,
        email="rubric-student@example.com",
        role=UserRole.STUDENT,
    )
    outsider_student = _create_user(
        test_session_factory,
        email="rubric-outsider-student@example.com",
        role=UserRole.STUDENT,
    )
    administrator = _create_user(
        test_session_factory,
        email="rubric-admin@example.com",
        role=UserRole.ADMIN,
    )
    course_id = _create_course(
        test_session_factory,
        faculty=[owner, peer_faculty],
        students=[student],
    )
    owner_headers = _headers(owner, test_settings)
    peer_headers = _headers(peer_faculty, test_settings)
    outsider_faculty_headers = _headers(outsider_faculty, test_settings)
    student_headers = _headers(student, test_settings)
    outsider_student_headers = _headers(outsider_student, test_settings)
    admin_headers = _headers(administrator, test_settings)

    unauthenticated = await client.post(
        "/api/v1/rubrics",
        json={"course_id": str(course_id), "title": "Argumentative Essay"},
    )
    assert unauthenticated.status_code == 401
    student_create = await client.post(
        "/api/v1/rubrics",
        json={"course_id": str(course_id), "title": "Argumentative Essay"},
        headers=student_headers,
    )
    assert student_create.status_code == 403

    create = await client.post(
        "/api/v1/rubrics",
        json={
            "course_id": str(course_id),
            "title": "Argumentative Essay",
            "description": "Measures the quality of an argument.",
        },
        headers=owner_headers,
    )
    assert create.status_code == 201
    rubric = create.json()
    rubric_id = rubric["id"]
    assert rubric["status"] == RubricStatus.DRAFT.value

    outsider_create = await client.post(
        "/api/v1/rubrics",
        json={"course_id": str(course_id), "title": "Outsider Rubric"},
        headers=outsider_faculty_headers,
    )
    assert outsider_create.status_code == 404

    initial_versions = await client.get(
        f"/api/v1/rubrics/{rubric_id}/versions",
        headers=owner_headers,
    )
    assert initial_versions.status_code == 200
    assert len(initial_versions.json()) == 1
    version_id = initial_versions.json()[0]["id"]
    assert initial_versions.json()[0]["criteria"] == []

    empty_publish = await client.post(
        f"/api/v1/rubric-versions/{version_id}/publish",
        headers=owner_headers,
    )
    assert empty_publish.status_code == 409

    invalid_weights = await client.put(
        f"/api/v1/rubric-versions/{version_id}/criteria",
        json={"criteria": _criteria(("0.4", "0.5"))},
        headers=owner_headers,
    )
    assert invalid_weights.status_code == 422

    zero_weight_criteria = _criteria()
    zero_weight_criteria[0]["weight"] = "0"
    zero_weight = await client.put(
        f"/api/v1/rubric-versions/{version_id}/criteria",
        json={"criteria": zero_weight_criteria},
        headers=owner_headers,
    )
    assert zero_weight.status_code == 422

    invalid_range_criteria = _criteria()
    invalid_range_criteria[0]["min_score"] = "4"
    invalid_range = await client.put(
        f"/api/v1/rubric-versions/{version_id}/criteria",
        json={"criteria": invalid_range_criteria},
        headers=owner_headers,
    )
    assert invalid_range.status_code == 422

    invalid_level_criteria = _criteria()
    invalid_level_criteria[0]["levels"] = [
        {"score": "5", "description": "Outside the criterion score range."}
    ]
    invalid_level = await client.put(
        f"/api/v1/rubric-versions/{version_id}/criteria",
        json={"criteria": invalid_level_criteria},
        headers=owner_headers,
    )
    assert invalid_level.status_code == 422

    before_publish = await client.get(
        "/api/v1/rubrics",
        headers=student_headers,
    )
    assert before_publish.status_code == 200
    assert before_publish.json() == []
    student_draft = await client.get(
        f"/api/v1/rubrics/{rubric_id}",
        headers=student_headers,
    )
    assert student_draft.status_code == 404

    save_criteria = await client.put(
        f"/api/v1/rubric-versions/{version_id}/criteria",
        json={"criteria": _criteria()},
        headers=owner_headers,
    )
    assert save_criteria.status_code == 200
    assert len(save_criteria.json()["criteria"]) == 2
    assert save_criteria.json()["criteria"][0]["levels"][1]["score"] == "4"

    peer_read = await client.get(
        f"/api/v1/rubrics/{rubric_id}",
        headers=peer_headers,
    )
    assert peer_read.status_code == 200
    peer_edit = await client.put(
        f"/api/v1/rubric-versions/{version_id}/criteria",
        json={"criteria": _criteria()},
        headers=peer_headers,
    )
    assert peer_edit.status_code == 404
    outsider_read = await client.get(
        f"/api/v1/rubrics/{rubric_id}",
        headers=outsider_faculty_headers,
    )
    assert outsider_read.status_code == 404
    outsider_student_read = await client.get(
        f"/api/v1/rubrics/{rubric_id}",
        headers=outsider_student_headers,
    )
    assert outsider_student_read.status_code == 404

    publish = await client.post(
        f"/api/v1/rubric-versions/{version_id}/publish",
        headers=owner_headers,
    )
    assert publish.status_code == 200
    published_snapshot = deepcopy(publish.json()["snapshot"])
    assert publish.json()["is_published"] is True
    assert len(published_snapshot["criteria"]) == 2

    published_rubric = await client.get(
        f"/api/v1/rubrics/{rubric_id}",
        headers=student_headers,
    )
    assert published_rubric.status_code == 200
    assert published_rubric.json()["status"] == RubricStatus.PUBLISHED.value
    student_versions = await client.get(
        f"/api/v1/rubrics/{rubric_id}/versions",
        headers=student_headers,
    )
    assert [version["id"] for version in student_versions.json()] == [version_id]
    student_version = await client.get(
        f"/api/v1/rubric-versions/{version_id}",
        headers=student_headers,
    )
    assert student_version.status_code == 200

    edit_published = await client.put(
        f"/api/v1/rubric-versions/{version_id}/criteria",
        json={"criteria": _criteria()},
        headers=owner_headers,
    )
    assert edit_published.status_code == 409
    edit_published_metadata = await client.patch(
        f"/api/v1/rubrics/{rubric_id}",
        json={"title": "Changed after publication"},
        headers=owner_headers,
    )
    assert edit_published_metadata.status_code == 409

    create_v2 = await client.post(
        f"/api/v1/rubrics/{rubric_id}/versions",
        headers=owner_headers,
    )
    assert create_v2.status_code == 201
    version_2 = create_v2.json()
    version_2_id = version_2["id"]
    assert version_2["version_number"] == 2
    assert version_2["is_published"] is False
    assert [criterion["name"] for criterion in version_2["criteria"]] == [
        "Analysis",
        "Evidence",
    ]
    another_pending_version = await client.post(
        f"/api/v1/rubrics/{rubric_id}/versions",
        headers=owner_headers,
    )
    assert another_pending_version.status_code == 409
    assert [version["id"] for version in (
        await client.get(
            f"/api/v1/rubrics/{rubric_id}/versions",
            headers=student_headers,
        )
    ).json()] == [version_id]

    updated_criteria = _criteria(("0.5", "0.5"))
    updated_criteria[0]["name"] = "Critical Analysis"
    save_v2 = await client.put(
        f"/api/v1/rubric-versions/{version_2_id}/criteria",
        json={"criteria": updated_criteria},
        headers=owner_headers,
    )
    assert save_v2.status_code == 200
    publish_v2 = await client.post(
        f"/api/v1/rubric-versions/{version_2_id}/publish",
        headers=owner_headers,
    )
    assert publish_v2.status_code == 200

    first_version_again = await client.get(
        f"/api/v1/rubric-versions/{version_id}",
        headers=owner_headers,
    )
    assert first_version_again.json()["snapshot"] == published_snapshot
    assert first_version_again.json()["criteria"][0]["name"] == "Analysis"
    published_versions_after_v2 = await client.get(
        f"/api/v1/rubrics/{rubric_id}/versions",
        headers=student_headers,
    )
    assert [
        version["version_number"]
        for version in published_versions_after_v2.json()
    ] == [1, 2]

    archive = await client.post(
        f"/api/v1/rubrics/{rubric_id}/archive",
        headers=owner_headers,
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == RubricStatus.ARCHIVED.value
    assert (await client.get("/api/v1/rubrics", headers=student_headers)).json() == []
    archived_student_get = await client.get(
        f"/api/v1/rubrics/{rubric_id}",
        headers=student_headers,
    )
    assert archived_student_get.status_code == 404
    archived_student_version = await client.get(
        f"/api/v1/rubric-versions/{version_2_id}",
        headers=student_headers,
    )
    assert archived_student_version.status_code == 404
    admin_get = await client.get(
        f"/api/v1/rubrics/{rubric_id}",
        headers=admin_headers,
    )
    assert admin_get.status_code == 200
    assert admin_get.json()["status"] == RubricStatus.ARCHIVED.value

    archived_new_version = await client.post(
        f"/api/v1/rubrics/{rubric_id}/versions",
        headers=owner_headers,
    )
    assert archived_new_version.status_code == 409
    archived_again = await client.post(
        f"/api/v1/rubrics/{rubric_id}/archive",
        headers=owner_headers,
    )
    assert archived_again.status_code == 409
    archived_metadata_edit = await client.patch(
        f"/api/v1/rubrics/{rubric_id}",
        json={"title": "Archived edit"},
        headers=owner_headers,
    )
    assert archived_metadata_edit.status_code == 409


@pytest.mark.asyncio
async def test_rubric_metadata_patch_and_admin_read_permissions(
    client: AsyncClient,
    test_session_factory: sessionmaker,
    test_settings: Settings,
) -> None:
    owner = _create_user(
        test_session_factory,
        email="rubric-metadata-owner@example.com",
        role=UserRole.FACULTY,
    )
    student = _create_user(
        test_session_factory,
        email="rubric-metadata-student@example.com",
        role=UserRole.STUDENT,
    )
    administrator = _create_user(
        test_session_factory,
        email="rubric-metadata-admin@example.com",
        role=UserRole.ADMIN,
    )
    course_id = _create_course(
        test_session_factory,
        faculty=[owner],
        students=[student],
    )

    create = await client.post(
        "/api/v1/rubrics",
        json={"course_id": str(course_id), "title": "Draft Rubric"},
        headers=_headers(owner, test_settings),
    )
    rubric_id = create.json()["id"]
    patch = await client.patch(
        f"/api/v1/rubrics/{rubric_id}",
        json={"title": "Updated Draft", "description": None},
        headers=_headers(owner, test_settings),
    )
    assert patch.status_code == 200
    assert patch.json()["title"] == "Updated Draft"
    assert patch.json()["description"] is None

    empty_patch = await client.patch(
        f"/api/v1/rubrics/{rubric_id}",
        json={},
        headers=_headers(owner, test_settings),
    )
    assert empty_patch.status_code == 422
    null_title = await client.patch(
        f"/api/v1/rubrics/{rubric_id}",
        json={"title": None},
        headers=_headers(owner, test_settings),
    )
    assert null_title.status_code == 422

    admin_list = await client.get(
        "/api/v1/rubrics",
        headers=_headers(administrator, test_settings),
    )
    assert [rubric["id"] for rubric in admin_list.json()] == [rubric_id]
    admin_create = await client.post(
        "/api/v1/rubrics",
        json={"course_id": str(course_id), "title": "Admin Rubric"},
        headers=_headers(administrator, test_settings),
    )
    assert admin_create.status_code == 403
