"""Account creation and password authentication."""

from datetime import datetime, timedelta, timezone
from secrets import compare_digest
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    create_refresh_token,
    dummy_password_hash,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.models.user import RefreshSession, User, UserRole


class UserAlreadyExistsError(ValueError):
    """Raised when an account already uses the requested email address."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(
    session: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole,
) -> User:
    user = add_user(
        session,
        email=email,
        password=password,
        full_name=full_name,
        role=role,
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise UserAlreadyExistsError from exc

    session.refresh(user)
    return user


def add_user(
    session: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole,
) -> User:
    normalized_email = normalize_email(email)
    existing = session.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise UserAlreadyExistsError

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        role=role,
        is_active=True,
    )
    session.add(user)
    return user


def authenticate_user(session: Session, *, email: str, password: str) -> User | None:
    user = session.scalar(
        select(User).where(User.email == normalize_email(email))
    )
    if user is None:
        verify_password(password, dummy_password_hash())
        return None
    password_matches = verify_password(password, user.password_hash)
    if not user.is_active or not password_matches:
        return None
    return user


def issue_refresh_session(
    session: Session,
    *,
    user: User,
    expires_days: int,
) -> str:
    raw_token = create_refresh_token()
    session.add(
        RefreshSession(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=expires_days),
        )
    )
    session.commit()
    return raw_token


def rotate_refresh_session(
    session: Session,
    *,
    raw_token: str,
    expires_days: int,
) -> tuple[User, str] | None:
    token_hash = hash_refresh_token(raw_token)
    refresh_session = session.scalar(
        select(RefreshSession)
        .where(RefreshSession.token_hash == token_hash)
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if refresh_session is None:
        return None
    if refresh_session.revoked_at is not None:
        revoke_refresh_family(session, family_id=refresh_session.family_id)
        return None
    expires_at = refresh_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now or not compare_digest(refresh_session.token_hash, token_hash):
        if expires_at <= now:
            refresh_session.revoked_at = now
            session.commit()
        return None

    user = session.get(User, refresh_session.user_id)
    if user is None or not user.is_active:
        revoke_refresh_family(session, family_id=refresh_session.family_id)
        return None

    refresh_session.revoked_at = now
    next_token = create_refresh_token()
    session.add(
        RefreshSession(
            user_id=user.id,
            family_id=refresh_session.family_id,
            token_hash=hash_refresh_token(next_token),
            expires_at=now + timedelta(days=expires_days),
        )
    )
    session.commit()
    return user, next_token


def revoke_refresh_session(
    session: Session,
    *,
    raw_token: str,
) -> None:
    refresh_session = session.scalar(
        select(RefreshSession)
        .where(RefreshSession.token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    )
    if refresh_session is not None:
        revoke_refresh_family(session, family_id=refresh_session.family_id)


def revoke_refresh_family(session: Session, *, family_id: UUID) -> None:
    now = datetime.now(timezone.utc)
    session.execute(
        update(RefreshSession)
        .where(RefreshSession.family_id == family_id)
        .values(revoked_at=func.coalesce(RefreshSession.revoked_at, now))
    )
    session.commit()
