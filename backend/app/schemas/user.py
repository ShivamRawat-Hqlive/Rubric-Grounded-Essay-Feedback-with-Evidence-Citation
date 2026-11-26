"""Authentication and user API schemas."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.db.models.user import UserRole


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RegistrationRequest(StrictRequest):
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)


class AdminUserCreateRequest(RegistrationRequest):
    role: UserRole


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginRequest(StrictRequest):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)
