"""phase_15a repair buggy backfill — strip api-keys:create

Revision ID: 79a8f0ad842e
Revises: 79604e21db28
Create Date: 2026-04-16

TASK-1451.12 — Codex xhigh review CRITICAL on PR #368.

Phase 15a (470bb55476a0) backfilled NULL-scope active API keys with a
"conservative" 11-scope set that incorrectly included ``api-keys:create``,
a RESTRICTED scope per ``src/auth/models.py``. Backfilled legacy keys
could then mint arbitrary scoped keys via ``/api/v2/admin/api-keys``,
contradicting TASK-1433.09's intent.

The Phase 15a migration is fixed in-place to omit ``api-keys:create`` from
the conservative set going forward, but several internal databases have
already had the buggy 11-scope array applied. This forward-repair migration
rewrites those rows to the corrected 10-scope array.

Match condition: ``scopes::jsonb`` exactly equal to the original buggy
sorted 11-scope array. Rows that already have the corrected 10-scope array,
rows with any other shape (e.g. legitimate admin keys that include
``api-keys:create`` alongside other scopes), and rows with NULL scopes are
all left untouched.

Idempotency: a second run matches zero rows because the corrected rows no
longer equal the buggy 11-scope array.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "79a8f0ad842e"
down_revision: str | Sequence[str] | None = "79604e21db28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_BUGGY_SCOPES = sorted(
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
        "api-keys:create",
    ]
)
_NEW_CONSERVATIVE_SCOPES = [s for s in _OLD_BUGGY_SCOPES if s != "api-keys:create"]


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE api_keys SET scopes = CAST(:new AS jsonb) "
            "WHERE scopes::jsonb = CAST(:old AS jsonb)"
        ),
        {
            "new": json.dumps(_NEW_CONSERVATIVE_SCOPES),
            "old": json.dumps(_OLD_BUGGY_SCOPES),
        },
    )


def downgrade() -> None:
    pass
