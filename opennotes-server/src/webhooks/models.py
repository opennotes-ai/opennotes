from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, text
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
    community_server_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
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
    community_server_id: Mapped[str] = mapped_column(String(50), nullable=True, index=True)
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


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"), index=True
    )
    task_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    interaction_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    interaction_token: Mapped[str] = mapped_column(String(200), nullable=False)
    application_id: Mapped[str] = mapped_column(String(50), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    task_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
