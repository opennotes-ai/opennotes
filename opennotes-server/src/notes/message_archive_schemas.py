from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema
from src.notes.message_archive_models import ContentType


class MessageArchiveBase(BaseModel):
    content_type: str = Field(..., description="Type of content (text, image, video, file)")
    content_text: str | None = Field(None, description="Text content for text messages")
    content_url: str | None = Field(None, description="URL for images and videos")
    file_reference: str | None = Field(None, description="File reference for file attachments")
    image_description: str | None = Field(
        None, description="AI-generated description for image content"
    )
    message_metadata: dict[str, Any] | None = Field(None, description="Flexible metadata storage")
    platform_message_id: str | None = Field(
        None, description="Platform message ID (e.g., Discord, Reddit)"
    )
    platform_channel_id: str | None = Field(
        None, description="Platform channel ID (e.g., Discord, Reddit)"
    )
    platform_author_id: str | None = Field(
        None, description="Platform author ID (e.g., Discord, Reddit)"
    )
    platform_timestamp: datetime | None = Field(
        None, description="Platform message timestamp (optional)"
    )

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        valid_types = [ContentType.TEXT, ContentType.IMAGE, ContentType.VIDEO, ContentType.FILE]
        v_lower = v.lower()
        if v_lower not in valid_types:
            raise ValueError(f"content_type must be one of {valid_types}, got '{v}'")
        return v_lower


class MessageArchiveCreate(MessageArchiveBase, StrictInputSchema):
    pass


class MessageArchiveResponse(MessageArchiveBase, SQLAlchemySchema):
    id: UUID = Field(..., description="Unique message archive ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")
    deleted_at: datetime | None = Field(None, description="Soft delete timestamp")
