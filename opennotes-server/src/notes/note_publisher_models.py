from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.llm_config.models import CommunityServer
    from src.notes.models import Note


class NotePublisherPost(Base):
    """
    Tracks published notes to prevent duplicates and provide audit trail.

    Each record represents an attempt to publish a note as a Discord reply
    when it crossed the scoring threshold with sufficient confidence.
    """

    __tablename__ = "note_publisher_posts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True,
    )

    # Note reference
    note_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )

    # Discord message references
    original_message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    auto_post_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Discord location
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Relationship to CommunityServer
    community_server: Mapped[CommunityServer] = relationship("CommunityServer", lazy="joined")

    # Score metadata at time of posting
    score_at_post: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_at_post: Mapped[str] = mapped_column(String(32), nullable=False)

    # Audit trail
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship to Note (using string to allow deferred import)
    note: Mapped[Note] = relationship(
        "Note", back_populates="note_publisher_posts", foreign_keys=[note_id]
    )

    __table_args__ = (
        # Ensure only one published note per original message (prevents duplicate posting)
        # Indexes are created by Alembic migration, not by model definition
        UniqueConstraint("original_message_id", name="uq_note_publisher_posts_original_message"),
    )


class NotePublisherConfig(Base):
    """
    Per-server and per-channel configuration for note publishing behavior.

    Supports both server-wide settings (channel_id=None) and channel-specific
    overrides (channel_id set). Channel-specific settings take precedence.
    """

    __tablename__ = "note_publisher_config"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"), index=True
    )

    # Discord location (channel_id=None means server-wide)
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Relationship to CommunityServer
    community_server: Mapped[CommunityServer] = relationship("CommunityServer", lazy="joined")

    # Configuration
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Audit trail
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        # One config per community_server+channel combination
        # Indexes are created by Alembic migration, not by model definition
        UniqueConstraint(
            "community_server_id",
            "channel_id",
            name="uq_note_publisher_config_community_server_channel",
        ),
    )


from src.notes.models import Note  # noqa: E402
