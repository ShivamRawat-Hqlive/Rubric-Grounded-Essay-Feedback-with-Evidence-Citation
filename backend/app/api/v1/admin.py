"""Administrator-only user administration endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.models.user import User, UserRole
from app.db.session import get_db
from app.schemas.user import AdminUserCreateRequest, UserResponse
from app.services.auth import UserAlreadyExistsError, create_user

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=list[UserResponse])
def list_users(
    _admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[Session, Depends(get_db)],
) -> list[User]:
    return list(session.scalars(select(User).order_by(User.created_at.desc())))


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_managed_user(
    request: AdminUserCreateRequest,
    _admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[Session, Depends(get_db)],
) -> User:
    try:
        return create_user(
            session,
            email=str(request.email),
            password=request.password.get_secret_value(),
            full_name=request.full_name,
            role=request.role,
        )
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
