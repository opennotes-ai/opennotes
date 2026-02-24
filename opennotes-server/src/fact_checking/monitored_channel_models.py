from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pendulum
from sqlalchemy import (
    ARRAY,
    Boolean,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from src.database import Base

if TYPE_CHECKING:
    from src.llm_config.models import CommunityServer


class MonitoredChannel(Base):
    """
    Configuration for Discord channels monitored for potential misinformation.

    Allows community administrators to opt-in specific channels for automatic
    fact-checking against available datasets. Each channel can have custom
    similarity thresholds and dataset filtering.

    Attributes:
        id: Unique identifier (UUID)
        community_server_id: Discord server/guild ID (platform-agnostic naming)
        channel_id: Discord channel ID
        enabled: Whether monitoring is active for this channel
        similarity_threshold: Minimum similarity score (0.0-1.0) for matches
        dataset_tags: List of dataset tags to check against (e.g., ['snopes', 'politifact'])
        created_at: Timestamp when monitoring was configured
        updated_at: Timestamp of last configuration update
        updated_by: Discord user ID of admin who last updated configuration
    """

    __tablename__ = "monitored_channels"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, index=True
    )

    # Discord location identifiers
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationship to CommunityServer
    community_server: Mapped[CommunityServer] = relationship("CommunityServer", lazy="joined")

    # Configuration
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    similarity_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.75"
    )
    dataset_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )

    # Previously seen message thresholds (NULL = use config defaults)
    previously_seen_autopublish_threshold: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Override threshold for auto-publishing previously seen notes (NULL = use config default)",
    )
    previously_seen_autorequest_threshold: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Override threshold for auto-requesting notes on previously seen content (NULL = use config default)",
    )

    # Audit trail
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: pendulum.now("UTC"),
    )
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Indexes and constraints
    __table_args__ = (
        # Ensure one config per channel
        UniqueConstraint("channel_id", name="uq_monitored_channels_channel_id"),
        # Composite index for common query pattern (server + enabled channels)
        Index("idx_monitored_channels_server_enabled", "community_server_id", "enabled"),
        # Index for dataset tag filtering
        Index("idx_monitored_channels_dataset_tags", "dataset_tags", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return (
            f"<MonitoredChannel(id={self.id}, channel={self.channel_id}, "
            f"enabled={self.enabled}, threshold={self.similarity_threshold})>"
        )
