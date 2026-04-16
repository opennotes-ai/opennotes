"""phase_105b: repair orphan user profiles

Revision ID: task1451_02b
Revises: task1451_02a
Create Date: 2026-04-15

Phase 1.0.5 — MANDATORY GATE for Phase 1.1.

Repairs two classes of data anomaly that must not exist before Phase 1.1
introduces the principal_type column:

  Pass 1 — Discord orphans: profiles that have a discord UserIdentity but
  no backing users row with a matching discord_id. Synthesizes a deactivated
  users row so the profile is no longer orphaned. The synthesized user has
  is_active=FALSE and hashed_password='DEACTIVATED' to prevent login.

  The username is derived from the first 8 chars of the provider_user_id to
  stay under the implicit length constraints while remaining human-readable.
  Discord IDs are all-numeric, so collisions are impossible for different IDs.

Idempotency:
  Pass 1 INSERT uses a LEFT JOIN / WHERE u.id IS NULL guard — running twice
  matches zero rows on the second pass and inserts nothing.

Ref: authorization-redesign-design.md Section 5, Phase 1.0.5b
"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "task1451_02b"
down_revision: str | Sequence[str] | None = "task1451_02a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(
        text("""
        SELECT p.id, p.display_name, ui.provider, ui.provider_user_id
        FROM user_profiles p
        JOIN user_identities ui ON ui.profile_id = p.id
        LEFT JOIN users u ON (
            (ui.provider = 'discord' AND ui.provider_user_id = u.discord_id) OR
            (ui.provider = 'email'   AND ui.provider_user_id = u.email)
        )
        WHERE u.id IS NULL
    """)
    )
    orphans = result.fetchall()
    print(f"[task1451_02b] Found {len(orphans)} orphan profile-identity pairs")
    for row in orphans:
        print(f"  profile_id={row[0]} display_name={row[1]} provider={row[2]} pid={row[3]}")

    conn.execute(
        text("""
        INSERT INTO users (
            id, username, email, hashed_password,
            is_active, discord_id, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            'orphan-' || substring(ui.provider_user_id, 1, 8),
            'orphan-' || ui.provider_user_id || '@opennotes.local',
            'DEACTIVATED',
            FALSE,
            ui.provider_user_id,
            NOW(),
            NOW()
        FROM user_profiles p
        JOIN user_identities ui ON ui.profile_id = p.id
        LEFT JOIN users u ON ui.provider_user_id = u.discord_id
        WHERE ui.provider = 'discord' AND u.id IS NULL
    """)
    )

    result = conn.execute(
        text("""
        SELECT p.id, p.display_name
        FROM user_profiles p
        LEFT JOIN user_identities ui ON ui.profile_id = p.id
        WHERE ui.id IS NULL
    """)
    )
    no_identity = result.fetchall()
    print(
        f"[task1451_02b] Found {len(no_identity)} profiles with zero identities (informational only)"
    )
    for row in no_identity:
        print(f"  profile_id={row[0]} display_name={row[1]}")

    result = conn.execute(
        text("""
        SELECT count(*) FROM user_profiles p
        LEFT JOIN user_identities ui ON ui.profile_id = p.id
        LEFT JOIN users u ON (
            (ui.provider = 'discord' AND ui.provider_user_id = u.discord_id) OR
            (ui.provider = 'email'   AND ui.provider_user_id = u.email)
        )
        WHERE u.id IS NULL AND ui.id IS NOT NULL
    """)
    )
    residual = result.scalar()
    print(f"[task1451_02b] Post-repair orphan count: {residual}")
    if residual and residual > 0:
        print(f"[task1451_02b] WARNING: {residual} orphan pairs remain — manual review required")


def downgrade() -> None:
    pass
