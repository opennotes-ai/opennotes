"""phase_15b: deactivate active API keys with empty-array scopes

Revision ID: cfb0d3ca43cf
Revises: 470bb55476a0
Create Date: 2026-04-15

Phase 1.5 — fixes TASK-1433.09 (NULL scopes = unrestricted access bug).

After the has_scope() fix, an empty-array scopes value means zero access.
Any active key with scopes=[] is effectively useless — it cannot authorize
any request. Deactivating these keys removes dead credentials from the system
rather than leaving them as inert entries that could confuse auditors.

Idempotency: WHERE scopes = '[]'::jsonb AND is_active = TRUE matches zero rows
on a second run once all such keys are already deactivated.

Ref: authorization-redesign-design.md Section 5, Phase 1.5
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "cfb0d3ca43cf"
down_revision: str | Sequence[str] | None = "470bb55476a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE api_keys
           SET is_active = FALSE
         WHERE scopes = '[]'::jsonb
           AND is_active = TRUE
    """)


def downgrade() -> None:
    pass
