"""backfill_embedding_provider_litellm_to_openai

Revision ID: 1185d275f39b
Revises: 1dceabf5c87e
Create Date: 2026-03-27 16:00:31.641626

"""

from collections.abc import Sequence

from alembic import op

revision: str = "1185d275f39b"
down_revision: str | Sequence[str] | None = "1dceabf5c87e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE fact_check_items SET embedding_provider = 'openai' "
        "WHERE embedding_provider = 'litellm'"
    )
    op.execute(
        "UPDATE chunk_embeddings SET embedding_provider = 'openai' "
        "WHERE embedding_provider = 'litellm'"
    )
    op.execute(
        "UPDATE previously_seen_messages SET embedding_provider = 'openai' "
        "WHERE embedding_provider = 'litellm'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE fact_check_items SET embedding_provider = 'litellm' "
        "WHERE embedding_provider = 'openai'"
    )
    op.execute(
        "UPDATE chunk_embeddings SET embedding_provider = 'litellm' "
        "WHERE embedding_provider = 'openai'"
    )
    op.execute(
        "UPDATE previously_seen_messages SET embedding_provider = 'litellm' "
        "WHERE embedding_provider = 'openai'"
    )
