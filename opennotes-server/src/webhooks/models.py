from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    secret: Mapped[str] = mapped_column(String(100), nullable=False)
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[str] = mapped_column(String(50), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"), index=True
    )
    interaction_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    interaction_type: Mapped[int] = mapped_column(Integer, nullable=False)
    community_server_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id"),
        nullable=True,
        index=True,
    )
    channel_id: Mapped[str] = mapped_column(String(50), nullable=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    command_name: Mapped[str] = mapped_column(String(100), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    response_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    response_type: Mapped[int] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
