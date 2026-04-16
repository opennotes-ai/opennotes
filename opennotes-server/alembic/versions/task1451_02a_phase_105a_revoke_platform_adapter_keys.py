"""phase_105a: revoke all pre-existing platform:adapter API keys

Revision ID: task1451_02a
Revises: f718d7324989
Create Date: 2026-04-15

Phase 1.0.5 — MANDATORY GATE for Phase 1.1.

Deactivates all API keys that carry the platform:adapter scope. These keys
were issued before the authorization redesign and bypass the principal-type
access model that Phase 1.1 will enforce.

Idempotency: UPDATE with a WHERE clause on a boolean flag is safe to run
multiple times — second run matches zero rows and does nothing.

Ref: authorization-redesign-design.md Section 5, Phase 1.0.5a
"""

from collections.abc import Sequence

from alembic import op

revision: str = "task1451_02a"
down_revision: str | Sequence[str] | None = "f718d7324989"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE api_keys
           SET is_active = FALSE
         WHERE scopes @> '["platform:adapter"]'::jsonb
    """)


def downgrade() -> None:
    pass
