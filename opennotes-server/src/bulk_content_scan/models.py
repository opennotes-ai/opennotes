from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.notes.models import TimestampMixin

if TYPE_CHECKING:
    from src.community_config.models import CommunityServer
    from src.users.profile_models import UserProfile


class BulkContentScanLog(Base, TimestampMixin):
    """Log of bulk content scans performed per community server."""

    __tablename__ = "bulk_content_scan_logs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True,
    )
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    initiated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scan_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    messages_scanned: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    messages_flagged: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="in_progress", nullable=False)

    community_server: Mapped[CommunityServer] = relationship("CommunityServer", lazy="raise")
    initiated_by: Mapped[UserProfile | None] = relationship("UserProfile", lazy="raise")
