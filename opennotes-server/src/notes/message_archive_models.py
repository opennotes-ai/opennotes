from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ContentType:
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    FILE = "file"


class MessageArchive(Base):
    __tablename__ = "message_archive"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )

    # Content type determines which content field is populated
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Content fields - one will be populated based on content_type
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    file_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # AI-generated image description for image content types
    image_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Flexible metadata storage (named message_metadata to avoid conflict with SQLAlchemy's metadata)
    message_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    platform_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    platform_channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    platform_author_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    platform_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamp fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Indexes for common queries
    __table_args__ = (
        Index("idx_message_archive_created_at", "created_at"),
        Index("idx_message_archive_deleted_at", "deleted_at"),
        Index("idx_message_archive_platform_message", "platform_message_id", "platform_channel_id"),
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def get_content(self) -> str | None:
        if self.content_type == ContentType.TEXT:
            return self.content_text
        if self.content_type in (ContentType.IMAGE, ContentType.VIDEO):
            return self.content_url
        if self.content_type == ContentType.FILE:
            return self.file_reference
        return None

    def soft_delete(self) -> None:
        self.deleted_at = datetime.now(UTC)
