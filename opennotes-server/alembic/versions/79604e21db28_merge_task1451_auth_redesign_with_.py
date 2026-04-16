"""merge_task1451_auth_redesign_with_task1401

Revision ID: 79604e21db28
Revises: 8939f7cda382, task1401_17
Create Date: 2026-04-16 12:53:10.226077

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79604e21db28'
down_revision: Union[str, Sequence[str], None] = ('8939f7cda382', 'task1401_17')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
