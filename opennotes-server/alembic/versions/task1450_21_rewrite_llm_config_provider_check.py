"""Rewrite ck_llm_config_provider CHECK constraint to match factory keys.

Revision ID: task1450_21
Revises: task1450_09
Create Date: 2026-04-20

TASK-1450.21 — follow-up to TASK-1450.13. The `LLMConfigCreate.provider` /
`LLMConfigTestRequest.provider` Pydantic Literal was tightened to
``("openai", "anthropic", "vertex_ai")`` matching ``LLMProviderFactory._providers``.
The DB-level CHECK constraint ``ck_llm_config_provider`` on
``community_server_llm_config`` (introduced in migration ``94badc57d821``)
still enumerates the stale set
``('openai', 'anthropic', 'google', 'cohere', 'custom')``. Rows written with
the new ``vertex_ai`` canonical value would be rejected by the DB.

This migration:

1. Rewrites any existing ``community_server_llm_config.provider`` values that
   reference providers no longer supported (``gemini`` → ``vertex_ai``,
   ``google`` → ``vertex_ai``) so surviving rows satisfy the tightened constraint.
2. Leaves ``cohere`` and ``custom`` alone — there is no safe mapping. If any
   exist they will fail the new CHECK and require operator cleanup.
3. Drops and re-adds ``ck_llm_config_provider`` with the new value set
   ``('openai', 'anthropic', 'vertex_ai')``.

Idempotency: the ``DROP CONSTRAINT IF EXISTS`` guard makes re-application a
no-op once the constraint is at the new shape; the UPDATE statements' WHERE
clauses match only legacy values.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "task1450_21"
down_revision: str | Sequence[str] | None = "task1450_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the old constraint first so the UPDATE below doesn't violate it
    # while rewriting 'google'/'gemini' rows to 'vertex_ai'. The new, tighter
    # constraint goes on at the end.
    op.execute(
        "ALTER TABLE community_server_llm_config DROP CONSTRAINT IF EXISTS ck_llm_config_provider"
    )
    op.execute(
        """
        UPDATE community_server_llm_config
           SET provider = 'vertex_ai'
         WHERE provider IN ('gemini', 'google')
        """
    )
    op.execute(
        """
        ALTER TABLE community_server_llm_config
        ADD CONSTRAINT ck_llm_config_provider
        CHECK (provider IN ('openai', 'anthropic', 'vertex_ai'))
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "TASK-1450.21 downgrade not supported: restoring the old CHECK set would "
        "re-admit providers (google, cohere, custom) the runtime no longer supports."
    )
