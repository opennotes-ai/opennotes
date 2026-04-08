"""enable RLS on moderation_actions and webhook_deliveries

Revision ID: task1428_01
Revises: task1400_06_06
Create Date: 2026-04-08

"""

from collections.abc import Sequence

from alembic import op

revision: str = "task1428_01"
down_revision: str | Sequence[str] | None = "task1400_06_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    "moderation_actions",
    "webhook_deliveries",
]

POLICIES = [
    (
        "moderation_actions",
        "Members can read community moderation actions",
        "SELECT",
        "(SELECT public.is_community_member(community_server_id))",
    ),
]


def upgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT (SELECT relrowsecurity FROM pg_class WHERE relname = '{table}') THEN
                    EXECUTE 'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY';
                    EXECUTE 'ALTER TABLE {table} FORCE ROW LEVEL SECURITY';
                END IF;
            END
            $$;
        """)

    for table, name, cmd, qual in POLICIES:
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policy WHERE polname = '{name}'
                    AND polrelid = '{table}'::regclass
                ) THEN
                    EXECUTE 'CREATE POLICY "{name}" ON {table} FOR {cmd} TO authenticated USING ({qual})';
                END IF;
            END
            $$;
        """)


def downgrade() -> None:
    for table, name, _, _ in reversed(POLICIES):
        op.execute(f'DROP POLICY IF EXISTS "{name}" ON {table}')

    for table in reversed(RLS_TABLES):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
