"""User profile endpoints with owner/admin authorization."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User, UserRole
from app.db.session import get_db
from app.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}", response_model=UserResponse)
def read_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> User:
    if current_user.id != user_id and current_user.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user
