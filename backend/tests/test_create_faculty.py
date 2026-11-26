import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.security import verify_password
from app.db.models.user import User, UserRole
from app.scripts import create_faculty
from app.services.auth import create_user


def _provide_prompts(
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str,
    email: str,
    passwords: tuple[str, str],
) -> None:
    answers = iter((name, email))
    password_answers = iter(passwords)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(create_faculty, "getpass", lambda _prompt: next(password_answers))


def test_create_faculty_cli_hashes_password_and_does_not_print_it(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    test_session_factory: sessionmaker,
) -> None:
    password = "local-faculty-demo-password"
    _provide_prompts(
        monkeypatch,
        name="Demo Faculty",
        email="FACULTY@example.com",
        passwords=(password, password),
    )
    monkeypatch.setattr(
        create_faculty,
        "get_session_factory",
        lambda: test_session_factory,
    )

    create_faculty.main()

    with test_session_factory() as session:
        faculty = session.scalar(
            select(User).where(User.email == "faculty@example.com")
        )
        assert faculty is not None
        assert faculty.full_name == "Demo Faculty"
        assert faculty.role is UserRole.FACULTY
        assert faculty.password_hash != password
        assert verify_password(password, faculty.password_hash)

    output = capsys.readouterr().out
    assert "Faculty account created." in output
    assert password not in output


def test_create_faculty_cli_rejects_duplicate_email_without_modifying_account(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
) -> None:
    with test_session_factory() as session:
        existing = create_user(
            session,
            email="faculty@example.com",
            password="existing-faculty-password",
            full_name="Existing Faculty",
            role=UserRole.FACULTY,
        )
        existing_id = existing.id

    _provide_prompts(
        monkeypatch,
        name="Replacement Name",
        email="FACULTY@example.com",
        passwords=("another-faculty-password", "another-faculty-password"),
    )
    monkeypatch.setattr(
        create_faculty,
        "get_session_factory",
        lambda: test_session_factory,
    )

    with pytest.raises(SystemExit, match="already exists"):
        create_faculty.main()

    with test_session_factory() as session:
        users = list(session.scalars(select(User)))
        assert len(users) == 1
        assert users[0].id == existing_id
        assert users[0].full_name == "Existing Faculty"


def test_create_faculty_cli_does_not_disclose_invalid_password(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
) -> None:
    password = "too-short"
    _provide_prompts(
        monkeypatch,
        name="Demo Faculty",
        email="faculty@example.com",
        passwords=(password, password),
    )
    monkeypatch.setattr(
        create_faculty,
        "get_session_factory",
        lambda: test_session_factory,
    )

    with pytest.raises(SystemExit) as error:
        create_faculty.main()

    assert password not in str(error.value)
    with test_session_factory() as session:
        assert session.scalar(select(User.id)) is None
