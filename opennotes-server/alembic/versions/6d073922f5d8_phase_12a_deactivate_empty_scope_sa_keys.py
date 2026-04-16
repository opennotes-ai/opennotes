"""phase_12a_deactivate_empty_scope_sa_keys

Revision ID: 6d073922f5d8
Revises: 071d69f63f60
Create Date: 2026-04-15

Phase 1.2a — post-backfill data cleanup (003d).

Blanket-deactivates all API keys that:
  - Are held by a principal with principal_type IN ('agent', 'system')
  - Have an empty or NULL scopes array
  - Are currently active (is_active = TRUE)

Rationale: After Phase 1.1 backfilled principal_type, any non-human principal
holding a zero-scope key has no legitimate access surface. Such keys are
operationally useless and represent unnecessary attack surface. Human principal
keys are deliberately excluded — empty-scope human keys may be intentional.

Idempotency: The WHERE clause on is_active = TRUE ensures the second run
matches zero rows and does nothing.

Downgrade: Cannot reliably re-activate — operators must re-issue keys if needed.

Ref: authorization-redesign-design.md Section 5, Phase 1.2a
"""

from collections.abc import Sequence

from alembic import op

revision: str = "6d073922f5d8"
down_revision: str | Sequence[str] | None = "071d69f63f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE api_keys SET is_active = FALSE
        WHERE user_id IN (SELECT id FROM users WHERE principal_type IN ('agent','system'))
          AND (scopes IS NULL OR jsonb_array_length(scopes) = 0)
          AND is_active = TRUE
    """)


def downgrade() -> None:
    pass
