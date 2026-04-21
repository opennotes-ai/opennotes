"""Migrate opennotes_sim_agents.model_name to Gemini 3 SKUs on google-vertex.

Revision ID: task1450_09
Revises: 79a8f0ad842e
Create Date: 2026-04-20

TASK-1450.09 — one-shot data migration that rewrites every
``opennotes_sim_agents.model_name`` row to a Gemini 3 SKU on ``google-vertex``.

Lands AFTER production code drops ``google-gla`` (TASK-1450.06) and updates
defaults (TASK-1450.05) so no row ever points to a string the runtime refuses
to instantiate.

Rewrite plan (ordered, idempotent):

- ``google-gla:gemini-2.5-pro``                  -> ``google-vertex:gemini-3.1-pro-preview``
- ``google-vertex:gemini-2.5-pro``               -> ``google-vertex:gemini-3.1-pro-preview``
- ``google-vertex:global/gemini-2.5-pro``        -> ``google-vertex:gemini-3.1-pro-preview``
- ``google-gla:gemini-2.5-flash``                -> ``google-vertex:gemini-3-flash``
- ``google-vertex:gemini-2.5-flash``             -> ``google-vertex:gemini-3-flash``
- ``google-vertex:global/gemini-2.5-flash``      -> ``google-vertex:gemini-3-flash``
- ``google-gla:%`` (catch-all)                   -> ``google-vertex:gemini-3.1-pro-preview``

The ``google-vertex:global/...`` shapes come from the older
``vertex_ai/global/...`` slash format (see ``tests/unit/llm_config/test_model_id.py``)
that leaked into persisted rows before the runtime normalized them.

CRITICAL ORDERING: the specific 2.5-flash mappings (including the ``global/``
variant) run BEFORE the ``google-gla:%`` catch-all so that
``google-gla:gemini-2.5-flash`` is routed to ``gemini-3-flash`` rather than
collapsed into the pro preview.  The flash statement is also listed BEFORE
the pro statement in the module body to make the flash-first precedence
visually obvious, though flash and pro WHERE clauses are disjoint so either
order is sound.

Idempotency: every statement is ``UPDATE ... WHERE <legacy value>``. Re-running
after a successful apply matches zero rows because the target values (
``google-vertex:gemini-3.1-pro-preview``, ``google-vertex:gemini-3-flash``)
do not satisfy any of the WHERE clauses.

Downgrade is NOT supported: Gemini 2.5 SKUs retire on Vertex 2026-10-16. We
refuse the downgrade rather than resurrect strings the runtime will reject.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "task1450_09"
down_revision: str | Sequence[str] | None = "79a8f0ad842e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE opennotes_sim_agents
           SET model_name = 'google-vertex:gemini-3-flash'
         WHERE model_name = 'google-gla:gemini-2.5-flash'
            OR model_name = 'google-vertex:gemini-2.5-flash'
            OR model_name = 'google-vertex:global/gemini-2.5-flash'
        """
    )
    op.execute(
        """
        UPDATE opennotes_sim_agents
           SET model_name = 'google-vertex:gemini-3.1-pro-preview'
         WHERE model_name = 'google-gla:gemini-2.5-pro'
            OR model_name = 'google-vertex:gemini-2.5-pro'
            OR model_name = 'google-vertex:global/gemini-2.5-pro'
        """
    )
    op.execute(
        """
        UPDATE opennotes_sim_agents
           SET model_name = 'google-vertex:gemini-3.1-pro-preview'
         WHERE model_name LIKE 'google-gla:%'
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "TASK-1450.09 downgrade not supported: Gemini 2.5 retires on Vertex 2026-10-16."
    )
