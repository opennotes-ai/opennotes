"""RLS policies for playground-facing tables

Revision ID: d6267cf7c0d0
Revises: 458c433da8d8
Create Date: 2026-03-13 15:00:08.066130

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d6267cf7c0d0"
down_revision: str | Sequence[str] | None = "458c433da8d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUTH_STUB_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth') THEN
        CREATE SCHEMA auth;
        CREATE OR REPLACE FUNCTION auth.uid()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        AS 'SELECT NULL::uuid';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
END
$$;
"""

AUTH_STUB_TEARDOWN_SQL = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'auth' AND p.proname = 'uid'
        AND p.prosrc = 'SELECT NULL::uuid'
    ) THEN
        DROP FUNCTION IF EXISTS auth.uid();
        DROP SCHEMA IF EXISTS auth;
    END IF;
    BEGIN
        DROP ROLE IF EXISTS authenticated;
    EXCEPTION WHEN dependent_objects_still_exist THEN
        NULL;
    END;
    BEGIN
        DROP ROLE IF EXISTS anon;
    EXCEPTION WHEN dependent_objects_still_exist THEN
        NULL;
    END;
END
$$;
"""

MEMBERSHIP_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION public.is_community_member(p_community_server_id uuid)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.community_members
        WHERE community_id = p_community_server_id
        AND profile_id = (SELECT auth.uid())
        AND is_active = true
    );
$$;
"""

POLICIES = [
    (
        "user_profiles",
        "Users can read own profile",
        "SELECT",
        "id = (SELECT auth.uid())",
    ),
    (
        "community_servers",
        "Members can read their communities",
        "SELECT",
        "(SELECT public.is_community_member(id))",
    ),
    (
        "community_members",
        "Users can read own memberships",
        "SELECT",
        "profile_id = (SELECT auth.uid())",
    ),
    (
        "community_members",
        "Users can update own memberships",
        "UPDATE",
        "profile_id = (SELECT auth.uid())",
    ),
    (
        "notes",
        "Members can read community notes",
        "SELECT",
        "(SELECT public.is_community_member(community_server_id)) AND deleted_at IS NULL",
    ),
    (
        "ratings",
        "Users can read own ratings",
        "SELECT",
        "rater_id = (SELECT auth.uid())",
    ),
    (
        "ratings",
        "Users can insert own ratings",
        "INSERT",
        "rater_id = (SELECT auth.uid())",
    ),
    (
        "ratings",
        "Users can update own ratings",
        "UPDATE",
        "rater_id = (SELECT auth.uid())",
    ),
    (
        "requests",
        "Members can read community requests",
        "SELECT",
        "(SELECT public.is_community_member(community_server_id)) AND deleted_at IS NULL",
    ),
    (
        "message_archive",
        "Members can read community messages",
        "SELECT",
        """EXISTS (
            SELECT 1 FROM public.requests r
            WHERE r.message_archive_id = message_archive.id
            AND (SELECT public.is_community_member(r.community_server_id))
            AND r.deleted_at IS NULL
        )""",
    ),
    (
        "scoring_snapshots",
        "Members can read community scoring",
        "SELECT",
        "(SELECT public.is_community_member(community_server_id))",
    ),
    (
        "simulation_runs",
        "Members can read community simulations",
        "SELECT",
        "(SELECT public.is_community_member(community_server_id)) AND deleted_at IS NULL",
    ),
]


def upgrade() -> None:
    op.execute(AUTH_STUB_SQL)
    op.execute(MEMBERSHIP_FUNCTION_SQL)

    for table, name, cmd, qual in POLICIES:
        if cmd == "INSERT":
            op.execute(
                f'CREATE POLICY "{name}" ON {table} FOR {cmd} TO authenticated WITH CHECK ({qual})'
            )
        else:
            op.execute(
                f'CREATE POLICY "{name}" ON {table} FOR {cmd} TO authenticated USING ({qual})'
            )


def downgrade() -> None:
    for table, name, _, _ in reversed(POLICIES):
        op.execute(f'DROP POLICY IF EXISTS "{name}" ON {table}')

    op.execute("DROP FUNCTION IF EXISTS public.is_community_member(uuid)")
    op.execute(AUTH_STUB_TEARDOWN_SQL)
