"""Registration, login, and authenticated identity endpoints."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_signing_key
from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.db.models.user import User, UserRole
from app.db.session import get_db
from app.schemas.user import (
    AccessTokenResponse,
    LoginRequest,
    RegistrationRequest,
    UserResponse,
)
from app.services.auth import (
    UserAlreadyExistsError,
    authenticate_user,
    create_user,
    issue_refresh_session,
    revoke_refresh_session,
    rotate_refresh_session,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
REFRESH_COOKIE_NAME = "essay_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(
    response: Response,
    *,
    token: str,
    settings: Settings,
) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response, *, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegistrationRequest,
    session: Annotated[Session, Depends(get_db)],
) -> User:
    try:
        return create_user(
            session,
            email=str(request.email),
            password=request.password.get_secret_value(),
            full_name=request.full_name,
            role=UserRole.STUDENT,
        )
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc


@router.post("/login", response_model=AccessTokenResponse)
def login(
    request: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    signing_key: Annotated[str, Depends(get_signing_key)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccessTokenResponse:
    user = authenticate_user(
        session,
        email=str(request.email),
        password=request.password.get_secret_value(),
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    refresh_token = issue_refresh_session(
        session,
        user=user,
        expires_days=settings.refresh_token_expire_days,
    )
    set_refresh_cookie(response, token=refresh_token, settings=settings)
    return AccessTokenResponse(
        access_token=create_access_token(user.id, signing_key, settings.jwt_access_token_expire_minutes),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    signing_key: Annotated[str, Depends(get_signing_key)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> AccessTokenResponse:
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    rotated = rotate_refresh_session(
        session,
        raw_token=refresh_token,
        expires_days=settings.refresh_token_expire_days,
    )
    if rotated is None:
        clear_refresh_cookie(response, settings=settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    user, next_refresh_token = rotated
    set_refresh_cookie(response, token=next_refresh_token, settings=settings)
    return AccessTokenResponse(
        access_token=create_access_token(user.id, signing_key, settings.jwt_access_token_expire_minutes),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
def read_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> Response:
    if refresh_token is not None:
        revoke_refresh_session(
            session,
            raw_token=refresh_token,
        )
    clear_refresh_cookie(response, settings=settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
