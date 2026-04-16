"""phase_15a: backfill NULL scopes on active API keys

Revision ID: 470bb55476a0
Revises: 6d073922f5d8
Create Date: 2026-04-15

Phase 1.5 — fixes TASK-1433.09 (NULL scopes = unrestricted access bug).

Active API keys with NULL scopes get a conservative non-privileged scope set:
ALLOWED_API_KEY_SCOPES minus the keys of PRIVILEGED_SCOPE_REQUIREMENTS
(i.e., minus "platform:adapter") and minus RESTRICTED_SCOPES
(i.e., minus "api-keys:create"). This preserves existing access for
legitimate integrations while removing the implicit super-power and
without letting legacy keys mint new scoped keys.

Inactive keys with NULL scopes are backfilled to `[]` (empty array) so that
migration 15c (ALTER COLUMN scopes SET NOT NULL) does not fail on legacy
inactive rows. Empty scopes on inactive keys is safe — has_scope() returns
False regardless and the key cannot authenticate.

Idempotency: the active-keys UPDATE matches zero rows on a second run once
all active keys have been backfilled; the inactive-keys UPDATE is also a
no-op once all NULLs are gone.

Ref: authorization-redesign-design.md Section 5, Phase 1.5
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "470bb55476a0"
down_revision: str | Sequence[str] | None = "6d073922f5d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSERVATIVE_SCOPES = sorted(
    [
        "simulations:read",
        "requests:read",
        "requests:write",
        "notes:read",
        "notes:write",
        "notes:delete",
        "ratings:write",
        "profiles:read",
        "community-servers:read",
        "moderation-actions:read",
    ]
)


def upgrade() -> None:
    import json

    scopes_json = json.dumps(_CONSERVATIVE_SCOPES)
    conn = op.get_bind()
    # Active NULL-scope keys: backfill with conservative scope set
    conn.execute(
        sa.text(
            "UPDATE api_keys SET scopes = CAST(:scopes AS jsonb) WHERE scopes IS NULL AND is_active = TRUE"
        ),
        {"scopes": scopes_json},
    )
    # Inactive NULL-scope keys: backfill with empty array so migration 15c
    # (ALTER COLUMN SET NOT NULL) doesn't fail on legacy inactive keys.
    # Empty scopes on inactive keys is safe — has_scope() returns False anyway.
    conn.execute(sa.text("UPDATE api_keys SET scopes = '[]'::jsonb WHERE scopes IS NULL"))


def downgrade() -> None:
    pass
