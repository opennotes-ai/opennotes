"""Migrate plaintext refresh tokens to hashed tokens

Revision ID: 4d775d88463a
Revises: 9af63353f83d
Create Date: 2025-10-30 16:29:03.875933

"""

from collections.abc import Sequence

import bcrypt
import sqlalchemy as sa
from sqlalchemy.sql import column, table

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4d775d88463a"
down_revision: str | Sequence[str] | None = "9af63353f83d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - hash existing plaintext tokens."""
    conn = op.get_bind()

    refresh_tokens = table(
        "refresh_tokens",
        column("id", sa.Integer),
        column("token", sa.String),
        column("token_hash", sa.String),
    )

    rows = conn.execute(
        sa.select(refresh_tokens.c.id, refresh_tokens.c.token).where(
            sa.and_(refresh_tokens.c.token.isnot(None), refresh_tokens.c.token_hash.is_(None))
        )
    ).fetchall()

    for row in rows:
        token_id = row[0]
        plaintext_token = row[1]

        password_bytes = plaintext_token.encode("utf-8")
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        token_hash = hashed.decode("utf-8")

        conn.execute(
            sa.update(refresh_tokens)
            .where(refresh_tokens.c.id == token_id)
            .values(token_hash=token_hash, token=None)
        )


def downgrade() -> None:
    """Downgrade schema - cannot restore plaintext tokens from hashes."""
