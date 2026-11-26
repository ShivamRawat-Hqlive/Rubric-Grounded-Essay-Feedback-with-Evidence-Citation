"""Interactively create the first administrator account."""

from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.core.config import ConfigurationError
from app.db.models.user import User, UserRole
from app.db.session import get_session_factory
from app.schemas.user import RegistrationRequest
from app.services.auth import UserAlreadyExistsError, create_user


def main() -> None:
    email_input = input("Admin email: ").strip()
    full_name = input("Admin full name: ").strip()
    password = getpass("Admin password (12+ characters): ")
    if password != getpass("Confirm admin password: "):
        raise SystemExit("Passwords did not match.")

    try:
        email = str(TypeAdapter(EmailStr).validate_python(email_input))
        account = RegistrationRequest(
            email=email,
            password=password,
            full_name=full_name,
        )
    except ValidationError as exc:
        raise SystemExit(f"Invalid admin account details: {exc}") from exc

    try:
        session_factory = get_session_factory()
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from exc

    with session_factory() as session:
        admin_exists = session.scalar(
            select(User.id).where(User.role == UserRole.ADMIN).limit(1)
        )
        if admin_exists is not None:
            raise SystemExit("An administrator already exists.")

        try:
            create_user(
                session,
                email=str(account.email),
                password=account.password.get_secret_value(),
                full_name=account.full_name,
                role=UserRole.ADMIN,
            )
        except UserAlreadyExistsError as exc:
            raise SystemExit("An account with this email already exists.") from exc

    print("First administrator account created.")


if __name__ == "__main__":
    main()
