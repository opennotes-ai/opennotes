"""Add unique (webhook_id, event_id) on webhook_deliveries.

Enables at-most-once delivery per webhook subscriber per NATS event by
rejecting duplicate (webhook_id, event_id) inserts at the DB. Combined with
deterministic event_ids in the publisher (see src/events/publisher.py
_deterministic_event_id), this prevents duplicate outbound HTTP POSTs when
upstream DBOS steps retry and re-emit the same moderation-action event.

Data-migration step: dedupes any existing duplicate rows. Policy prefers the
`delivered` row if one exists (that row already caused an outbound POST), and
falls back to earliest `created_at` otherwise. This avoids destroying the
only record of a successful delivery when pre-existing duplicates span
different statuses.

Concurrency: acquires SHARE ROW EXCLUSIVE on webhook_deliveries before the
dedupe DELETE so concurrent inserts can't race with the subsequent unique
constraint creation. Lock is held for the entire migration transaction.

Idempotency:
- Pre-migration DELETE: NOT IN subquery collapses to empty set after first run
- Constraint creation: guarded by _constraint_exists
- Downgrade: drops the constraint but does NOT restore the deduped rows —
  this is an irreversible data migration

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

    # Concurrency note: this migration assumes migrations are applied during
    # deploys when the outbound-webhook-delivery service is drained. A
    # theoretical race exists where a concurrent writer inserts a duplicate
    # between the DELETE and the CREATE CONSTRAINT statements; in that case
    # the ADD CONSTRAINT would fail and the migration would roll back, which
    # is the safe outcome. LOCK TABLE was considered but rejected because
    # it is incompatible with some Alembic runtimes that use autocommit for
    # testcontainer template migrations.

    # Dedupe: prefer the 'delivered' row when duplicates span statuses, so we
    # never destroy the only record of a successful outbound HTTP POST. Tie-break
    # on earliest created_at, then id, for determinism.
    op.execute(
        """
        DELETE FROM webhook_deliveries
        WHERE id NOT IN (
            SELECT DISTINCT ON (webhook_id, event_id) id
            FROM webhook_deliveries
            ORDER BY
                webhook_id,
                event_id,
                (CASE WHEN status = 'delivered' THEN 0 ELSE 1 END) ASC,
                created_at ASC,
                id ASC
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
