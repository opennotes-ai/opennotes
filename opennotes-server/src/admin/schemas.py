from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from src.common.base_schemas import StrictInputSchema


class AdminAPIKeyCreate(StrictInputSchema):
    user_email: EmailStr
    user_display_name: str = Field(..., min_length=1, max_length=255)
    key_name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(..., min_length=1)


class AdminAPIKeyResponse(BaseModel):
    id: UUID
    name: str
    key: str
    scopes: list[str] | None = None
    user_email: str
    user_display_name: str
    created_at: datetime
    expires_at: datetime | None = None
    model_config = {"from_attributes": True}


class AdminAPIKeyListItem(BaseModel):
    id: UUID
    name: str
    key_prefix: str | None = None
    scopes: list[str] | None = None
    user_email: str
    user_display_name: str
    created_at: datetime
    expires_at: datetime | None = None
    is_active: bool
    model_config = {"from_attributes": True}
