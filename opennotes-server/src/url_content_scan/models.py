from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base
from src.notes.models import TimestampMixin


class UrlScanState(Base):
    """Per-job header row for a URL scan.

    Job lifecycle state remains canonical on ``batch_jobs.status``. This table
    intentionally omits its own ``status`` column and the older monolithic
    ``sections`` JSONB shape.
    """

    __tablename__ = "url_scan_state"
    __table_args__ = (
        Index(
            "ix_url_scan_state_heartbeat_at_active",
            "heartbeat_at",
            postgresql_where=text("finished_at IS NULL"),
        ),
        Index(
            "ix_url_scan_state_finished_at_terminal",
            "finished_at",
            postgresql_where=text("finished_at IS NOT NULL"),
        ),
    )

    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("batch_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_host: Mapped[str | None] = mapped_column(Text, nullable=True)
    sidebar_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    utterance_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UrlScanSectionSlot(Base, TimestampMixin):
    """Per-section scan row.

    Writers must compare-and-swap on ``attempt_id`` when updating a slot row so
    a retried section supersedes stale workers without last-writer-wins races.
    """

    __tablename__ = "url_scan_section_slots"
    __table_args__ = (
        PrimaryKeyConstraint("job_id", "slug"),
        Index("ix_url_scan_section_slots_job_id_state", "job_id", "state"),
    )

    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("batch_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UrlScanScrape(Base):
    """Durable scrape metadata keyed by normalized URL and retrieval tier."""

    __tablename__ = "url_scan_scrapes"
    __table_args__ = (
        PrimaryKeyConstraint("normalized_url", "tier"),
        Index("ix_url_scan_scrapes_expires_at", "expires_at"),
    )

    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'scrape'"))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    page_kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'other'"))
    page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UrlScanUtterance(Base):
    """Per-job utterance cache row."""

    __tablename__ = "url_scan_utterances"
    __table_args__ = (PrimaryKeyConstraint("job_id", "utterance_id"),)

    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("batch_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    utterance_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class UrlScanWebRiskLookup(Base):
    """Web Risk findings cache keyed by normalized URL."""

    __tablename__ = "url_scan_web_risk_lookups"
    __table_args__ = (Index("ix_url_scan_web_risk_lookups_expires_at", "expires_at"),)

    normalized_url: Mapped[str] = mapped_column(Text, primary_key=True)
    findings: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UrlScanSidebarCache(Base):
    """Final sidebar payload cache keyed by normalized URL."""

    __tablename__ = "url_scan_sidebar_cache"
    __table_args__ = (Index("ix_url_scan_sidebar_cache_expires_at", "expires_at"),)

    normalized_url: Mapped[str] = mapped_column(Text, primary_key=True)
    sidebar_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
