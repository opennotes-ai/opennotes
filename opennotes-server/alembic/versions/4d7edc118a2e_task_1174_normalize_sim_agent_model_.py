"""task-1174: normalize sim_agent model_name to pydantic-ai format

Convert model_name values from LiteLLM slash format (provider/model)
to pydantic-ai colon format (provider:model), translating provider
names where they differ between the two ecosystems.

Downgrade limitation (task-1174.21):
    The upgrade skips values already in colon format (via `NOT LIKE '%:%'`),
    but the downgrade converts ALL colon-format values back to slash format
    unconditionally. If the table contained pre-existing colon-format entries
    before the upgrade, those rows would be left untouched by the upgrade but
    incorrectly converted to slash format on downgrade, making the rollback
    non-idempotent for mixed-format data.

    This is acceptable because:
    - Before this migration, no code path wrote colon-format model names, so
      pre-existing colon-format data is not expected in practice.
    - Migrations run inside a transaction and are only applied once.
    - Downgrades are rare in production and would only occur during an
      immediate rollback of this specific revision.

Revision ID: 4d7edc118a2e
Revises: 96eb91160c67
Create Date: 2026-02-25 12:29:02.429623

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4d7edc118a2e"
down_revision: str | Sequence[str] | None = "96eb91160c67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LITELLM_TO_PYDANTIC_PROVIDERS = {
    "vertex_ai": "google-vertex",
    "gemini": "google-gla",
}
PYDANTIC_TO_LITELLM_PROVIDERS = {v: k for k, v in LITELLM_TO_PYDANTIC_PROVIDERS.items()}


def upgrade() -> None:
    conn = op.get_bind()

    for litellm_provider, pydantic_provider in LITELLM_TO_PYDANTIC_PROVIDERS.items():
        conn.execute(
            sa.text(
                "UPDATE opennotes_sim_agents "
                "SET model_name = :new_prefix || substring(model_name from position('/' in model_name) + 1) "
                "WHERE model_name LIKE :pattern AND model_name NOT LIKE '%:%'"
            ),
            {"new_prefix": f"{pydantic_provider}:", "pattern": f"{litellm_provider}/%"},
        )

    conn.execute(
        sa.text(
            "UPDATE opennotes_sim_agents "
            "SET model_name = split_part(model_name, '/', 1) || ':' || "
            "substring(model_name from position('/' in model_name) + 1) "
            "WHERE model_name LIKE '%/%' AND model_name NOT LIKE '%:%'"
        )
    )


def downgrade() -> None:
    # WARNING: This downgrade assumes all colon-format entries were created by
    # the upgrade above. Any pre-existing colon-format values (which the upgrade
    # left untouched) will be incorrectly converted to slash format.
    # See the module docstring for full details on this limitation.
    conn = op.get_bind()

    for pydantic_provider, litellm_provider in PYDANTIC_TO_LITELLM_PROVIDERS.items():
        conn.execute(
            sa.text(
                "UPDATE opennotes_sim_agents "
                "SET model_name = :old_prefix || substring(model_name from position(':' in model_name) + 1) "
                "WHERE model_name LIKE :pattern"
            ),
            {"old_prefix": f"{litellm_provider}/", "pattern": f"{pydantic_provider}:%"},
        )

    conn.execute(
        sa.text(
            "UPDATE opennotes_sim_agents "
            "SET model_name = split_part(model_name, ':', 1) || '/' || "
            "substring(model_name from position(':' in model_name) + 1) "
            "WHERE model_name LIKE '%:%'"
        )
    )
