import importlib
import sys
from pathlib import Path

import pytest

from src.users.crud import verify_api_key

PLATFORM_DEV_API_KEY = "opk_platform_dev_api_keys_create_2026"
PLATFORM_SCOPES = ["api-keys:create"]


@pytest.mark.asyncio
async def test_platform_service_account_created_with_correct_flags(db_session):
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    seed_mod = importlib.import_module("seed_api_keys")

    await seed_mod.seed_platform_api_key(db_session)
    await db_session.commit()

    from sqlalchemy import text

    result = await db_session.execute(
        text("SELECT principal_type, platform_roles FROM users WHERE username = :username"),
        {"username": "platform-service"},
    )
    row = result.first()

    assert row is not None, "platform-service user must exist after seeding"
    principal_type, platform_roles = row
    assert principal_type == "system", "platform-service must be a system principal"
    assert "platform_admin" in platform_roles, "platform-service must have platform_admin role"


@pytest.mark.asyncio
async def test_platform_key_has_api_keys_create_scope(db_session):
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    seed_mod = importlib.import_module("seed_api_keys")

    await seed_mod.seed_platform_api_key(db_session)
    await db_session.commit()

    result = await verify_api_key(db_session, PLATFORM_DEV_API_KEY)
    assert result is not None, "platform dev API key must authenticate"

    api_key_obj, authenticated_user = result
    assert authenticated_user.username == "platform-service"
    assert api_key_obj.is_active is True
    assert api_key_obj.scopes == PLATFORM_SCOPES


@pytest.mark.asyncio
async def test_platform_seed_idempotent(db_session):
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    seed_mod = importlib.import_module("seed_api_keys")

    await seed_mod.seed_platform_api_key(db_session)
    await db_session.commit()

    await seed_mod.seed_platform_api_key(db_session)
    await db_session.commit()

    from sqlalchemy import text

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM users WHERE username = :username"),
        {"username": "platform-service"},
    )
    count = result.scalar_one()
    assert count == 1, "idempotent seeding must not duplicate the user"

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM api_keys WHERE name = :name"),
        {"name": "Platform (Development)"},
    )
    count = result.scalar_one()
    assert count == 1, "idempotent seeding must not duplicate the API key"


@pytest.mark.asyncio
async def test_platform_seed_rotates_stale_prefix_on_active_row(db_session):
    """TASK-1462.01 regression guard.

    Pre-seed an active row with a WRONG key_prefix (e.g. left over from an
    older GSM version whose plaintext prefix didn't match). Re-running the
    dev seed must atomically rewrite BOTH key_hash AND key_prefix to
    'platform', the prefix implied by PLATFORM_DEV_API_KEY. After the fix,
    verify_api_key's prefix-based O(1) lookup lands on the row, the hash
    matches, and auth succeeds. Pre-fix, the row would retain 'stale' and
    the prefix lookup would return None → 401.
    """
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    seed_mod = importlib.import_module("seed_api_keys")

    from sqlalchemy import text

    from src.auth.password import get_password_hash

    await db_session.execute(
        text("""
            INSERT INTO users (username, email, hashed_password, full_name,
                               is_active, principal_type, platform_roles,
                               created_at, updated_at)
            VALUES ('platform-service', 'platform@opennotes.local',
                    :pw, 'Platform Service Account',
                    TRUE, 'system', '["platform_admin"]'::json,
                    NOW(), NOW())
        """),
        {"pw": get_password_hash("throwaway")},
    )

    user_row = await db_session.execute(
        text("SELECT id FROM users WHERE username = :u"), {"u": "platform-service"}
    )
    user_id = user_row.scalar_one()

    stale_hash = get_password_hash("opk_stale_wrong_platform_plaintext_to_rotate_out")
    await db_session.execute(
        text("""
            INSERT INTO api_keys (user_id, name, key_hash, key_prefix, is_active, scopes, created_at)
            VALUES (:user_id, 'Platform (Development)', :key_hash, 'stale',
                    TRUE, CAST(:scopes AS jsonb), NOW())
        """),
        {
            "user_id": user_id,
            "key_hash": stale_hash,
            "scopes": '["api-keys:create"]',
        },
    )
    await db_session.commit()

    await seed_mod.seed_platform_api_key(db_session)
    await db_session.commit()

    result = await verify_api_key(db_session, PLATFORM_DEV_API_KEY)
    assert result is not None, (
        "platform seed must atomically rewrite key_hash + key_prefix so the "
        "real PLATFORM_DEV_API_KEY authenticates via the prefix-based lookup"
    )
    api_key_obj, _ = result
    assert api_key_obj.key_prefix == "platform", (
        f"key_prefix must be rotated from 'stale' to 'platform'; got {api_key_obj.key_prefix!r}"
    )
