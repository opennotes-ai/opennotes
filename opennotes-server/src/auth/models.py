import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None
    expires_in: int


class TokenData(BaseModel):
    user_id: UUID
    username: str
    role: str
    iat: int | None = None


class RefreshTokenRequest(BaseModel):
    """Request body for refresh token endpoint."""

    refresh_token: str = Field(
        ..., description="The refresh token to use for getting a new access token"
    )


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError(
                "Password too long (max 72 bytes in UTF-8). Please use a shorter password."
            )

        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")

        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")

        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")

        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")

        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in v):
            raise ValueError(
                f"Password must contain at least one special character ({special_chars})"
            )

        return v


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    password: str | None = Field(None, min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str | None) -> str | None:
        if v is None:
            return v

        if len(v.encode("utf-8")) > 72:
            raise ValueError(
                "Password too long (max 72 bytes in UTF-8). Please use a shorter password."
            )

        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")

        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")

        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")

        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")

        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in v):
            raise ValueError(
                f"Password must contain at least one special character ({special_chars})"
            )

        return v


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    full_name: str | None
    role: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    username: str
    password: str


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expires_in_days: int | None = Field(None, gt=0, le=365)


class APIKeyResponse(BaseModel):
    id: UUID
    name: str
    key: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    action: str
    resource: str
    resource_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    @field_validator("details", mode="before")
    @classmethod
    def parse_details(cls, value: str | dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        try:
            result: Any = json.loads(value)
            if isinstance(result, dict):
                return result
            return None
        except (json.JSONDecodeError, TypeError):
            return None

    @field_serializer("details")
    def serialize_details(self, value: str | dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        try:
            result: Any = json.loads(value)
            if isinstance(result, dict):
                return result
            return None
        except (json.JSONDecodeError, TypeError):
            return None

    model_config = {"from_attributes": True}
