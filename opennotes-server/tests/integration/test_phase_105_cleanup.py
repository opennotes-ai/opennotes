"""Phase 1.0.5 — pre-existing state cleanup migrations."""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_migration_0015a_revokes_adapter_keys(db_session):
    """After 0015a SQL, zero active keys should have platform:adapter scope."""
    await db_session.execute(
        text("""
        INSERT INTO users (id, username, email, hashed_password, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), 'test-adapter-user', 'adapter@test.example', 'fakehash', true, NOW(), NOW())
        ON CONFLICT DO NOTHING
    """)
    )
    await db_session.flush()

    user_id_result = await db_session.execute(
        text("""
        SELECT id FROM users WHERE username = 'test-adapter-user'
    """)
    )
    user_id = user_id_result.scalar_one()

    await db_session.execute(
        text("""
        INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, scopes, is_active, created_at)
        VALUES (gen_random_uuid(), :user_id, 'adapter-key', 'hash-adapter-test', 'ak_',
                '["platform:adapter"]'::jsonb, true, NOW())
    """),
        {"user_id": str(user_id)},
    )

    await db_session.execute(
        text("""
        INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, scopes, is_active, created_at)
        VALUES (gen_random_uuid(), :user_id, 'multi-scope-key', 'hash-multi-test', 'ak_',
                '["platform:adapter", "notes:read"]'::jsonb, true, NOW())
    """),
        {"user_id": str(user_id)},
    )

    await db_session.execute(
        text("""
        INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, scopes, is_active, created_at)
        VALUES (gen_random_uuid(), :user_id, 'unrelated-key', 'hash-unrelated-test', 'ak_',
                '["notes:read"]'::jsonb, true, NOW())
    """),
        {"user_id": str(user_id)},
    )
    await db_session.flush()

    await db_session.execute(
        text("""
        UPDATE api_keys
           SET is_active = FALSE
         WHERE scopes @> '["platform:adapter"]'::jsonb
    """)
    )
    await db_session.flush()

    adapter_result = await db_session.execute(
        text("""
        SELECT count(*) FROM api_keys
        WHERE scopes @> '["platform:adapter"]'::jsonb AND is_active = TRUE
    """)
    )
    assert adapter_result.scalar() == 0

    unrelated_result = await db_session.execute(
        text("""
        SELECT count(*) FROM api_keys
        WHERE name = 'unrelated-key' AND is_active = TRUE
    """)
    )
    assert unrelated_result.scalar() == 1

    deactivated_result = await db_session.execute(
        text("""
        SELECT count(*) FROM api_keys
        WHERE scopes @> '["platform:adapter"]'::jsonb AND is_active = FALSE
    """)
    )
    assert deactivated_result.scalar() == 2


@pytest.mark.asyncio
async def test_migration_0015a_idempotent(db_session):
    """Running 0015a SQL twice leaves the same result."""
    await db_session.execute(
        text("""
        INSERT INTO users (id, username, email, hashed_password, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), 'test-idem-user', 'idem@test.example', 'fakehash', true, NOW(), NOW())
        ON CONFLICT DO NOTHING
    """)
    )
    await db_session.flush()

    user_id_result = await db_session.execute(
        text("""
        SELECT id FROM users WHERE username = 'test-idem-user'
    """)
    )
    user_id = user_id_result.scalar_one()

    await db_session.execute(
        text("""
        INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, scopes, is_active, created_at)
        VALUES (gen_random_uuid(), :user_id, 'idem-key', 'hash-idem-test', 'ak_',
                '["platform:adapter"]'::jsonb, true, NOW())
    """),
        {"user_id": str(user_id)},
    )
    await db_session.flush()

    for _ in range(2):
        await db_session.execute(
            text("""
            UPDATE api_keys
               SET is_active = FALSE
             WHERE scopes @> '["platform:adapter"]'::jsonb
        """)
        )
        await db_session.flush()

    result = await db_session.execute(
        text("""
        SELECT count(*) FROM api_keys
        WHERE scopes @> '["platform:adapter"]'::jsonb AND is_active = TRUE
    """)
    )
    assert result.scalar() == 0


@pytest.mark.asyncio
async def test_migration_0015b_creates_user_for_orphan_discord_profile(db_session):
    """After 0015b SQL, Discord orphan profiles have a backing User synthesized."""
    await db_session.execute(
        text("""
        INSERT INTO user_profiles (id, display_name, is_human, is_active)
        VALUES (gen_random_uuid(), 'Orphan Discord Profile', true, true)
    """)
    )
    await db_session.flush()

    profile_id_result = await db_session.execute(
        text("""
        SELECT id FROM user_profiles WHERE display_name = 'Orphan Discord Profile'
    """)
    )
    profile_id = profile_id_result.scalar_one()

    await db_session.execute(
        text("""
        INSERT INTO user_identities (id, profile_id, provider, provider_user_id)
        VALUES (gen_random_uuid(), :pid, 'discord', '999000111222')
    """),
        {"pid": str(profile_id)},
    )
    await db_session.flush()

    orphan_before = await db_session.execute(
        text("""
        SELECT count(*) FROM user_profiles p
        JOIN user_identities ui ON ui.profile_id = p.id
        LEFT JOIN users u ON (
            (ui.provider = 'discord' AND ui.provider_user_id = u.discord_id) OR
            (ui.provider = 'email'   AND ui.provider_user_id = u.email)
        )
        WHERE u.id IS NULL AND p.id = :pid
    """),
        {"pid": str(profile_id)},
    )
    assert orphan_before.scalar() > 0

    await db_session.execute(
        text("""
        INSERT INTO users (id, username, email, hashed_password, is_active, discord_id, created_at, updated_at)
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
    await db_session.flush()

    orphan_after = await db_session.execute(
        text("""
        SELECT count(*) FROM user_profiles p
        JOIN user_identities ui ON ui.profile_id = p.id
        LEFT JOIN users u ON (
            (ui.provider = 'discord' AND ui.provider_user_id = u.discord_id) OR
            (ui.provider = 'email'   AND ui.provider_user_id = u.email)
        )
        WHERE u.id IS NULL AND p.id = :pid
    """),
        {"pid": str(profile_id)},
    )
    assert orphan_after.scalar() == 0

    user_result = await db_session.execute(
        text("""
        SELECT username, email, is_active, discord_id FROM users
        WHERE discord_id = '999000111222'
    """)
    )
    user_row = user_result.fetchone()
    assert user_row is not None
    assert user_row.email == "orphan-999000111222@opennotes.local"
    assert user_row.is_active is False
    assert user_row.discord_id == "999000111222"


@pytest.mark.asyncio
async def test_migration_0015b_idempotent_orphan_repair(db_session):
    """Running 0015b SQL twice does not create duplicate User rows."""
    await db_session.execute(
        text("""
        INSERT INTO user_profiles (id, display_name, is_human, is_active)
        VALUES (gen_random_uuid(), 'Idem Orphan Profile', true, true)
    """)
    )
    await db_session.flush()

    profile_id_result = await db_session.execute(
        text("""
        SELECT id FROM user_profiles WHERE display_name = 'Idem Orphan Profile'
    """)
    )
    profile_id = profile_id_result.scalar_one()

    await db_session.execute(
        text("""
        INSERT INTO user_identities (id, profile_id, provider, provider_user_id)
        VALUES (gen_random_uuid(), :pid, 'discord', '777888999000')
    """),
        {"pid": str(profile_id)},
    )
    await db_session.flush()

    for _ in range(2):
        await db_session.execute(
            text("""
            INSERT INTO users (id, username, email, hashed_password, is_active, discord_id, created_at, updated_at)
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
        await db_session.flush()

    count_result = await db_session.execute(
        text("""
        SELECT count(*) FROM users WHERE discord_id = '777888999000'
    """)
    )
    assert count_result.scalar() == 1


@pytest.mark.asyncio
async def test_post_audit_adapter_keys_zero_residual(db_session):
    """Post-audit query for 0015a returns zero active platform:adapter keys after migration."""
    await db_session.execute(
        text("""
        INSERT INTO users (id, username, email, hashed_password, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), 'audit-user-0015a', 'audit-0015a@test.example', 'fakehash', true, NOW(), NOW())
        ON CONFLICT DO NOTHING
    """)
    )
    await db_session.flush()

    user_id_result = await db_session.execute(
        text("""
        SELECT id FROM users WHERE username = 'audit-user-0015a'
    """)
    )
    user_id = user_id_result.scalar_one()

    await db_session.execute(
        text("""
        INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, scopes, is_active, created_at)
        VALUES (gen_random_uuid(), :user_id, 'audit-adapter-key', 'hash-audit-0015a', 'ak_',
                '["platform:adapter"]'::jsonb, true, NOW())
    """),
        {"user_id": str(user_id)},
    )
    await db_session.flush()

    await db_session.execute(
        text("""
        UPDATE api_keys
           SET is_active = FALSE
         WHERE scopes @> '["platform:adapter"]'::jsonb
    """)
    )
    await db_session.flush()

    result = await db_session.execute(
        text("""
        SELECT count(*) FROM api_keys
        WHERE scopes @> '["platform:adapter"]'::jsonb AND is_active = TRUE
    """)
    )
    assert result.scalar() == 0


@pytest.mark.asyncio
async def test_post_audit_orphan_profiles_zero_residual(db_session):
    """Post-audit query for 0015b returns zero orphan profile-identity pairs after migration."""
    await db_session.execute(
        text("""
        INSERT INTO user_profiles (id, display_name, is_human, is_active)
        VALUES (gen_random_uuid(), 'Audit Orphan Profile', true, true)
    """)
    )
    await db_session.flush()

    profile_id_result = await db_session.execute(
        text("""
        SELECT id FROM user_profiles WHERE display_name = 'Audit Orphan Profile'
    """)
    )
    profile_id = profile_id_result.scalar_one()

    await db_session.execute(
        text("""
        INSERT INTO user_identities (id, profile_id, provider, provider_user_id)
        VALUES (gen_random_uuid(), :pid, 'discord', '555444333222')
    """),
        {"pid": str(profile_id)},
    )
    await db_session.flush()

    await db_session.execute(
        text("""
        INSERT INTO users (id, username, email, hashed_password, is_active, discord_id, created_at, updated_at)
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
    await db_session.flush()

    result = await db_session.execute(
        text("""
        SELECT count(*) FROM user_profiles p
        LEFT JOIN user_identities ui ON ui.profile_id = p.id
        LEFT JOIN users u ON (
            (ui.provider = 'discord' AND ui.provider_user_id = u.discord_id) OR
            (ui.provider = 'email'   AND ui.provider_user_id = u.email)
        )
        WHERE u.id IS NULL AND ui.id IS NOT NULL
          AND p.id = :pid
    """),
        {"pid": str(profile_id)},
    )
    assert result.scalar() == 0
