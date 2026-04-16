"""Add unique (webhook_id, event_id) on webhook_deliveries.

Enables at-most-once delivery per webhook subscriber per NATS event by
rejecting duplicate (webhook_id, event_id) inserts at the DB. Combined with
deterministic event_ids in the publisher (see src/events/publisher.py
_deterministic_event_id), this gives exactly-once webhook delivery even when
upstream DBOS steps retry and re-emit the same moderation-action event.

Data-migration step: dedupes any existing duplicate rows by keeping the
earliest-created row per (webhook_id, event_id) and deleting the rest. Safe to
re-run — DELETE with NOT IN subquery is naturally idempotent (after first
run, no duplicates remain).

Revision ID: task1401_17
Revises: task1401_12
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "task1401_17"
down_revision: str | None = "task1401_12"
branch_labels: str | None = None
depends_on: str | None = None


_CONSTRAINT_NAME = "uq_webhook_deliveries_webhook_event"


def _constraint_exists(conn: sa.engine.Connection, name: str, table: str) -> bool:
    row = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            WHERE c.conname = :name AND t.relname = :table
            """
        ),
        {"name": name, "table": table},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()

    op.execute(
        """
        DELETE FROM webhook_deliveries
        WHERE id NOT IN (
            SELECT DISTINCT ON (webhook_id, event_id) id
            FROM webhook_deliveries
            ORDER BY webhook_id, event_id, created_at ASC, id ASC
        )
        """
    )

    if not _constraint_exists(conn, _CONSTRAINT_NAME, "webhook_deliveries"):
        op.create_unique_constraint(
            _CONSTRAINT_NAME,
            "webhook_deliveries",
            ["webhook_id", "event_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _constraint_exists(conn, _CONSTRAINT_NAME, "webhook_deliveries"):
        op.drop_constraint(_CONSTRAINT_NAME, "webhook_deliveries", type_="unique")
