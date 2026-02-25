from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pendulum
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.notes.message_archive_models import MessageArchive
    from src.users.profile_models import UserProfile


class TimestampMixin:
    """Mixin for adding created_at and updated_at timestamp fields to models."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )


class Note(Base, TimestampMixin):
    __tablename__ = "notes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True,
    )

    author_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )

    channel_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("requests.request_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(
        Enum("NOT_MISLEADING", "MISINFORMED_OR_POTENTIALLY_MISLEADING", name="note_classification"),
        nullable=False,
    )

    # Scoring results
    helpfulness_score: Mapped[int] = mapped_column(default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            "NEEDS_MORE_RATINGS",
            "CURRENTLY_RATED_HELPFUL",
            "CURRENTLY_RATED_NOT_HELPFUL",
            name="note_status",
        ),
        default="NEEDS_MORE_RATINGS",
        nullable=False,
    )

    # AI generation metadata
    ai_generated: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    ai_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Force-publish metadata (admin override)
    force_published: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    force_published_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    force_published_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships with lazy='raise' to prevent N+1 queries (explicit loading required)
    author: Mapped[UserProfile] = relationship(
        "UserProfile", foreign_keys=[author_id], lazy="raise"
    )
    force_published_by_profile: Mapped[UserProfile | None] = relationship(
        "UserProfile", foreign_keys=[force_published_by], lazy="raise"
    )
    ratings: Mapped[list[Rating]] = relationship(
        back_populates="note", lazy="raise", cascade="all, delete-orphan"
    )
    note_publisher_posts: Mapped[list[NotePublisherPost]] = relationship(
        back_populates="note", lazy="raise", cascade="all, delete-orphan"
    )
    request: Mapped[Request | None] = relationship(foreign_keys=[request_id], lazy="raise")

    # Indexes for common queries
    __table_args__ = (
        Index("idx_notes_created_at", "created_at"),
        Index("idx_notes_author_id", "author_id"),
        Index("idx_notes_status", "status"),
        Index("idx_notes_deleted_at", "deleted_at"),
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = pendulum.now("UTC")

    @property
    def author_display_name(self) -> str:
        """Get author display name from profile."""
        if self.author:
            return self.author.display_name
        return "Unknown"


class Rating(Base, TimestampMixin):
    __tablename__ = "ratings"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True,
    )

    rater_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )

    note_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    helpfulness_level: Mapped[str] = mapped_column(
        Enum("HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL", name="helpfulness_level"), nullable=False
    )

    # Relationships
    rater: Mapped[UserProfile] = relationship("UserProfile", foreign_keys=[rater_id], lazy="raise")
    note: Mapped[Note] = relationship("Note", back_populates="ratings", lazy="raise")

    # Indexes for common queries
    __table_args__ = (
        Index("idx_ratings_note_rater", "note_id", "rater_id", unique=True),
        Index("idx_ratings_created_at", "created_at"),
        Index("ix_ratings_rater_id", "rater_id"),
    )

    @property
    def rater_display_name(self) -> str:
        """Get rater display name from profile."""
        if self.rater:
            return self.rater.display_name
        return "Unknown"


class Request(Base, TimestampMixin):
    __tablename__ = "requests"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    community_server_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Message archive reference - optional to support backward compatibility
    message_archive_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("message_archive.id", ondelete="SET NULL"),
        nullable=True,
    )

    migrated_from_content: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", name="request_status"),
        default="PENDING",
        nullable=False,
    )
    note_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("notes.id", ondelete="SET NULL"), nullable=True
    )
    request_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, server_default="{}"
    )

    # Fact-check auto-creation fields
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    similarity_score: Mapped[float | None] = mapped_column(nullable=True)
    dataset_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dataset_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # UUID string

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships with lazy loading to avoid N+1 queries
    message_archive: Mapped[MessageArchive | None] = relationship(
        "MessageArchive", foreign_keys=[message_archive_id], lazy="selectin"
    )

    @property
    def content(self) -> str | None:
        """Get content from message archive.

        Returns content from message_archive if available, otherwise None.
        """
        if self.message_archive:
            return self.message_archive.get_content()
        return None

    # Indexes for common queries
    __table_args__ = (
        Index("idx_requests_status", "status"),
        Index("idx_requests_requested_at", "requested_at"),
        Index("idx_requests_message_archive", "message_archive_id"),
        Index("idx_requests_note_status", "note_id", "status"),
        Index("idx_requests_deleted_at", "deleted_at"),
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = pendulum.now("UTC")


from src.notes.message_archive_models import MessageArchive  # noqa: E402
from src.notes.note_publisher_models import NotePublisherPost  # noqa: E402
