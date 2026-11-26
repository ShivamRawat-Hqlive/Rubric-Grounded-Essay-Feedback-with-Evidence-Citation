"""Registration, login, and authorization integration tests."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.security import verify_password
from app.db.models.user import RefreshSession, User, UserRole
from app.scripts import seed
from app.services.auth import create_user


@pytest.mark.asyncio
async def test_register_creates_student_with_argon2id_hash_and_rejects_role(
    client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    payload = {
        "email": "Student@Example.com",
        "password": "correct horse battery staple",
        "full_name": "Test Student",
    }
    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "student@example.com"
    assert body["role"] == "student"
    assert "password" not in body
    assert "password_hash" not in body

    with test_session_factory() as session:
        user = session.scalar(
            select(User).where(User.email == "student@example.com")
        )
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(payload["password"], user.password_hash)
        assert user.role is UserRole.STUDENT

    role_escalation = await client.post(
        "/api/v1/auth/register",
        json={**payload, "email": "attacker@example.com", "role": "admin"},
    )
    assert role_escalation.status_code == 422

    duplicate = await client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 409
    invalid_email = await client.post(
        "/api/v1/auth/register",
        json={**payload, "email": "not-an-email"},
    )
    assert invalid_email.status_code == 422
    weak_password = await client.post(
        "/api/v1/auth/register",
        json={**payload, "email": "weak@example.com", "password": "short"},
    )
    assert weak_password.status_code == 422


@pytest.mark.asyncio
async def test_login_accepts_correct_password_and_rejects_incorrect_password(
    client: AsyncClient,
) -> None:
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "correct horse battery staple",
            "full_name": "Login Student",
        },
    )
    assert registration.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "LOGIN@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"
    refresh_token = login.cookies.get("essay_refresh")
    assert refresh_token is not None

    identity = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert identity.status_code == 200
    assert identity.json()["email"] == "login@example.com"

    wrong_password = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "incorrect password"},
    )
    assert wrong_password.status_code == 401
    assert wrong_password.json()["detail"] == "Invalid email or password."


@pytest.mark.asyncio
async def test_refresh_rotation_and_reuse_revoke_the_token_family(
    client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "password": "correct horse battery staple",
            "full_name": "Refresh Student",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "refresh@example.com",
            "password": "correct horse battery staple",
        },
    )
    first_refresh = login.cookies.get("essay_refresh")
    assert first_refresh is not None
    cookie_headers = login.headers.get_list("set-cookie")
    assert any("HttpOnly" in value and "SameSite=strict" in value for value in cookie_headers)

    with test_session_factory() as session:
        stored = session.scalar(select(RefreshSession))
        assert stored is not None
        assert stored.token_hash != first_refresh
        assert len(stored.token_hash) == 64
        initial_family_id = stored.family_id

    rotated = await client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    second_refresh = rotated.cookies.get("essay_refresh")
    assert second_refresh is not None
    assert second_refresh != first_refresh
    with test_session_factory() as session:
        rows = list(session.scalars(select(RefreshSession)))
        assert len(rows) == 2
        assert all(row.family_id == initial_family_id for row in rows)

    client.cookies.set("essay_refresh", first_refresh)
    reused = await client.post("/api/v1/auth/refresh")
    assert reused.status_code == 401
    client.cookies.set("essay_refresh", second_refresh)
    family_revoked = await client.post("/api/v1/auth/refresh")
    assert family_revoked.status_code == 401
    with test_session_factory() as session:
        assert all(
            row.revoked_at is not None
            for row in session.scalars(select(RefreshSession))
        )


@pytest.mark.asyncio
async def test_logout_revokes_refresh_family(
    client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout@example.com",
            "password": "correct horse battery staple",
            "full_name": "Logout Student",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "logout@example.com",
            "password": "correct horse battery staple",
        },
    )
    refresh_token = login.cookies.get("essay_refresh")
    assert refresh_token is not None
    logged_out = await client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 204

    client.cookies.set("essay_refresh", refresh_token)
    refresh_after_logout = await client.post("/api/v1/auth/refresh")
    assert refresh_after_logout.status_code == 401
    with test_session_factory() as session:
        stored = session.scalar(select(RefreshSession))
        assert stored is not None
        assert stored.revoked_at is not None


@pytest.mark.asyncio
async def test_expired_access_token_is_rejected(
    client: AsyncClient,
    test_session_factory: sessionmaker,
    test_settings: Settings,
) -> None:
    with test_session_factory() as session:
        user = create_user(
            session,
            email="expired@example.com",
            password="correct horse battery staple",
            full_name="Expired Student",
            role=UserRole.STUDENT,
        )
        user_id = user.id

    now = datetime.now(timezone.utc)
    signing_key = test_settings.jwt_secret_key.get_secret_value()
    expired_token = jwt.encode(
        {
            "sub": str(user_id),
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(seconds=1),
            "jti": "expired-test-token",
        },
        signing_key,
        algorithm="HS256",
    )
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_refresh_token_is_rejected(
    client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "expired-refresh@example.com",
            "password": "correct horse battery staple",
            "full_name": "Expired Refresh Student",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "expired-refresh@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert login.cookies.get("essay_refresh") is not None

    with test_session_factory() as session:
        session.execute(
            update(RefreshSession).values(
                expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
            )
        )
        session.commit()

    expired = await client.post("/api/v1/auth/refresh")
    assert expired.status_code == 401


def test_seed_command_creates_only_missing_roles(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
) -> None:
    email_inputs = iter(
        [
            "seed-admin@example.com",
            "Seed Admin",
            "seed-faculty@example.com",
            "Seed Faculty",
            "seed-student@example.com",
            "Seed Student",
        ]
    )
    passwords = iter(
        [
            "admin seed password long enough",
            "admin seed password long enough",
            "faculty seed password long enough",
            "faculty seed password long enough",
            "student seed password long enough",
            "student seed password long enough",
        ]
    )
    monkeypatch.setattr(seed, "get_session_factory", lambda: test_session_factory)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(email_inputs))
    monkeypatch.setattr(seed, "getpass", lambda _prompt: next(passwords))

    seed.main()

    with test_session_factory() as session:
        users = list(session.scalars(select(User)))
        assert {user.role for user in users} == set(UserRole)
        assert all(user.password_hash.startswith("$argon2id$") for user in users)


@pytest.mark.asyncio
async def test_login_is_rate_limited_per_client(
    client: AsyncClient,
) -> None:
    responses = []
    for _ in range(11):
        responses.append(
            await client.post(
                "/api/v1/auth/login",
                json={"email": "missing@example.com", "password": "invalid password"},
            )
        )

    assert all(response.status_code == 401 for response in responses[:10])
    assert responses[10].status_code == 429
    assert int(responses[10].headers["retry-after"]) > 0


@pytest.mark.asyncio
async def test_protected_routes_enforce_authentication_roles_and_ownership(
    client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    anonymous = await client.get("/api/v1/auth/me")
    assert anonymous.status_code == 401

    students = []
    for email in ("owner@example.com", "private@example.com"):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "correct horse battery staple",
                "full_name": email.split("@")[0],
            },
        )
        assert response.status_code == 201
        students.append(response.json())

    student_login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    student_token = student_login.json()["access_token"]
    student_headers = {"Authorization": f"Bearer {student_token}"}

    forbidden_admin_list = await client.get(
        "/api/v1/admin/users",
        headers=student_headers,
    )
    assert forbidden_admin_list.status_code == 403

    private_profile = await client.get(
        f"/api/v1/users/{students[1]['id']}",
        headers=student_headers,
    )
    assert private_profile.status_code == 404

    with test_session_factory() as session:
        admin = create_user(
            session,
            email="admin@example.com",
            password="admin password that is long enough",
            full_name="Test Admin",
            role=UserRole.ADMIN,
        )
        admin_id = admin.id
        assert isinstance(admin_id, UUID)

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "admin password that is long enough",
        },
    )
    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    admin_profile = await client.get(
        f"/api/v1/users/{students[1]['id']}",
        headers=admin_headers,
    )
    assert admin_profile.status_code == 200

    provisioned = await client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": "faculty@example.com",
            "password": "faculty password that is long enough",
            "full_name": "Test Faculty",
            "role": "faculty",
        },
    )
    assert provisioned.status_code == 201
    assert provisioned.json()["role"] == "faculty"

    faculty_login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "faculty@example.com",
            "password": "faculty password that is long enough",
        },
    )
    faculty_headers = {
        "Authorization": f"Bearer {faculty_login.json()['access_token']}"
    }
    faculty_admin_list = await client.get(
        "/api/v1/admin/users",
        headers=faculty_headers,
    )
    assert faculty_admin_list.status_code == 403
    faculty_private_profile = await client.get(
        f"/api/v1/users/{students[1]['id']}",
        headers=faculty_headers,
    )
    assert faculty_private_profile.status_code == 404

    users = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert users.status_code == 200
    assert len(users.json()) == 4
