"""Password hashing and JWT access-token helpers."""

import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError

password_hasher = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerificationError:
        return False


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


def create_access_token(
    subject: UUID,
    signing_key: str,
    expires_minutes: int,
) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(subject),
            "iat": now,
            "exp": now + timedelta(minutes=expires_minutes),
            "jti": secrets.token_urlsafe(16),
        },
        signing_key,
        algorithm="HS256",
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str, signing_key: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        signing_key,
        algorithms=["HS256"],
        options={"require": ["sub", "iat", "exp"]},
    )
