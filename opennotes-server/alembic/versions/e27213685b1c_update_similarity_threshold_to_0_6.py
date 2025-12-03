"""update_similarity_threshold_to_0_6

Update all monitored channels to use the new default similarity threshold of 0.6
instead of the previous default of 0.75.

This improves the sensitivity of fact-check matching, allowing more potential matches
to be surfaced for review.

Revision ID: e27213685b1c
Revises: af5f4322c2d1
Create Date: 2025-11-06 11:50:58.818019

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e27213685b1c"
down_revision: str | Sequence[str] | None = "af5f4322c2d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Update all monitored channels to use similarity_threshold of 0.6."""
    # Update all channels that are currently using the old default threshold (0.75)
    # or higher values to the new default (0.6)
    op.execute("""
        UPDATE monitored_channels
        SET similarity_threshold = 0.6
        WHERE similarity_threshold >= 0.75
    """)


def downgrade() -> None:
    """Revert similarity threshold changes back to 0.75."""
    # Revert all channels that were set to 0.6 back to the old default
    op.execute("""
        UPDATE monitored_channels
        SET similarity_threshold = 0.75
        WHERE similarity_threshold = 0.6
    """)
