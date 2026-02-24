from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class TokenPool(Base):
    __tablename__ = "token_pools"

    pool_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TokenHold(Base):
    __tablename__ = "token_holds"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True,
    )
    pool_name: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("token_pools.pool_name"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("pool_name", "workflow_id", name="uq_token_hold_pool_workflow"),
    )
