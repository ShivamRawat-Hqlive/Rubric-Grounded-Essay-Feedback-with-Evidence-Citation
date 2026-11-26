"""Dependencies shared by API routes."""

from typing import Annotated, Callable
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import ConfigurationError, Settings, get_settings
from app.core.security import decode_access_token
from app.db.models.user import User, UserRole
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def require_bearer_credentials(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> HTTPAuthorizationCredentials:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials


def get_signing_key(
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    try:
        return settings.require_jwt_secret()
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication is not configured.",
        ) from exc


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(require_bearer_credentials),
    ],
    session: Annotated[Session, Depends(get_db)],
    signing_key: Annotated[str, Depends(get_signing_key)],
) -> User:
    try:
        payload = decode_access_token(credentials.credentials, signing_key)
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*allowed_roles: UserRole) -> Callable[..., User]:
    def authorize(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return current_user

    return authorize
