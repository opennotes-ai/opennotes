from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base
from src.notes.models import TimestampMixin


class ActionState(str, Enum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    RETRO_REVIEW = "retro_review"
    CONFIRMED = "confirmed"
    OVERTURNED = "overturned"
    SCAN_EXEMPT = "scan_exempt"
    UNDER_REVIEW = "under_review"
    DISMISSED = "dismissed"


class ActionType(str, Enum):
    HIDE = "hide"
    UNHIDE = "unhide"
    WARN = "warn"
    SILENCE = "silence"
    DELETE = "delete"


class ActionTier(str, Enum):
    TIER_1_IMMEDIATE = "tier_1_immediate"
    TIER_2_CONSENSUS = "tier_2_consensus"


class ReviewGroup(str, Enum):
    COMMUNITY = "community"
    TRUSTED = "trusted"
    STAFF = "staff"


class ModerationAction(Base, TimestampMixin):
    __tablename__ = "moderation_actions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True,
    )

    request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("requests.id", ondelete="RESTRICT"),
        nullable=False,
    )

    note_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="SET NULL"),
        nullable=True,
    )

    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    action_type: Mapped[str] = mapped_column(String(50), nullable=False)

    action_tier: Mapped[str] = mapped_column(String(50), nullable=False)

    action_state: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'proposed'")
    )

    review_group: Mapped[str] = mapped_column(String(50), nullable=False)

    classifier_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    platform_action_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    scan_exempt_content_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    overturned_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    overturned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_moderation_actions_request_id", "request_id"),
        Index("ix_moderation_actions_note_id", "note_id"),
        Index("ix_moderation_actions_community_state", "community_server_id", "action_state"),
        sa.UniqueConstraint("request_id", "action_tier", name="uq_moderation_action_request_tier"),
    )
