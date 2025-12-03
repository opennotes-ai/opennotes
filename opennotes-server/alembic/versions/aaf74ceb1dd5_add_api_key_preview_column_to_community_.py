"""Add api_key_preview column to community_server_llm_config

Revision ID: aaf74ceb1dd5
Revises: 3cea1535ffca
Create Date: 2025-10-30 18:15:30.171115

"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aaf74ceb1dd5"
down_revision: str | Sequence[str] | None = "3cea1535ffca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "community_server_llm_config",
        sa.Column("api_key_preview", sa.String(length=20), nullable=True),
    )

    connection = op.get_bind()

    from src.llm_config.encryption import EncryptionService

    master_key = os.getenv("ENCRYPTION_MASTER_KEY")
    if not master_key:
        raise ValueError("ENCRYPTION_MASTER_KEY environment variable not set")

    encryption_service = EncryptionService(master_key)

    result = connection.execute(
        text("SELECT id, api_key_encrypted, encryption_key_id FROM community_server_llm_config")
    )

    for row in result:
        config_id = row[0]
        encrypted_key = bytes(row[1])
        key_id = row[2]

        try:
            api_key = encryption_service.decrypt_api_key(encrypted_key, key_id)
            preview = f"...{api_key[-4:]}" if len(api_key) >= 4 else "..."

            connection.execute(
                text(
                    "UPDATE community_server_llm_config SET api_key_preview = :preview WHERE id = :id"
                ),
                {"preview": preview, "id": config_id},
            )
        except Exception as e:
            print(f"Warning: Failed to decrypt API key for config {config_id}: {e}")
            connection.execute(
                text(
                    "UPDATE community_server_llm_config SET api_key_preview = '...' WHERE id = :id"
                ),
                {"id": config_id},
            )

    op.alter_column("community_server_llm_config", "api_key_preview", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("community_server_llm_config", "api_key_preview")
