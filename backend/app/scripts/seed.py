"""Interactively seed one account for each missing role."""

from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import ConfigurationError
from app.db.models.user import User, UserRole
from app.db.session import get_session_factory
from app.schemas.user import RegistrationRequest
from app.services.auth import UserAlreadyExistsError, add_user, normalize_email

SEED_ROLES = (UserRole.ADMIN, UserRole.FACULTY, UserRole.STUDENT)


def prompt_account(role: UserRole) -> tuple[UserRole, RegistrationRequest]:
    print(f"Create initial {role.value} account")
    email = input("Email: ").strip()
    full_name = input("Full name: ").strip()
    password = getpass("Password (12+ characters): ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords did not match.")

    try:
        account = RegistrationRequest(
            email=str(TypeAdapter(EmailStr).validate_python(email)),
            password=password,
            full_name=full_name,
        )
    except ValidationError as exc:
        raise SystemExit(
            "Invalid account details. Check the email, name, and password requirements."
        ) from exc
    return role, account


def main() -> None:
    try:
        session_factory = get_session_factory()
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from exc

    with session_factory() as session:
        existing_roles = set(session.scalars(select(User.role)).all())
        missing_roles = [role for role in SEED_ROLES if role not in existing_roles]
        if not missing_roles:
            print("Initial accounts for all roles already exist.")
            return

        accounts = [prompt_account(role) for role in missing_roles]
        account_emails = [normalize_email(str(account.email)) for _, account in accounts]
        if len(set(account_emails)) != len(account_emails):
            raise SystemExit("Each seeded role must use a distinct email address.")

        try:
            for role, account in accounts:
                add_user(
                    session,
                    email=str(account.email),
                    password=account.password.get_secret_value(),
                    full_name=account.full_name,
                    role=role,
                )
            session.commit()
        except UserAlreadyExistsError as exc:
            session.rollback()
            raise SystemExit(
                "A seeded email already belongs to an account; no seed accounts were committed."
            ) from exc
        except IntegrityError as exc:
            session.rollback()
            raise SystemExit(
                "The seed account transaction conflicted with existing data; no seed accounts were committed."
            ) from exc

    print("Initial role accounts created.")


if __name__ == "__main__":
    main()
