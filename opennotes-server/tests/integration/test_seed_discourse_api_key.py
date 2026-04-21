import importlib
import sys
from pathlib import Path

import pytest

from src.users.crud import verify_api_key

DISCOURSE_DEV_API_KEY = "opk_discourse_dev_platform_adapter_2026"
DISCOURSE_SCOPES = ["platform:adapter"]
DISCOURSE_USERNAME = "discourse-adapter-community-opennotes-ai"


@pytest.mark.asyncio
async def test_discourse_service_account_is_per_instance_agent(db_session):
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    seed_mod = importlib.import_module("seed_api_keys")

    await seed_mod.seed_discourse_api_key(db_session)
    await db_session.commit()

    from sqlalchemy import text

    result = await db_session.execute(
        text("SELECT principal_type, platform_roles FROM users WHERE username = :username"),
        {"username": DISCOURSE_USERNAME},
    )
    row = result.first()

    assert row is not None, "discourse adapter user must exist after seeding"
    principal_type, platform_roles = row
    assert principal_type == "agent", (
        "discourse adapter must be an agent principal (per-instance agent pattern)"
    )
    assert platform_roles == [], (
        "discourse adapter must NOT carry platform_admin — caller needs it, target does not"
    )


@pytest.mark.asyncio
async def test_discourse_key_has_platform_adapter_scope(db_session):
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    seed_mod = importlib.import_module("seed_api_keys")

    await seed_mod.seed_discourse_api_key(db_session)
    await db_session.commit()

    result = await verify_api_key(db_session, DISCOURSE_DEV_API_KEY)
    assert result is not None, "discourse dev API key must authenticate"

    api_key_obj, authenticated_user = result
    assert authenticated_user.username == DISCOURSE_USERNAME
    assert api_key_obj.is_active is True
    assert api_key_obj.scopes == DISCOURSE_SCOPES


@pytest.mark.asyncio
async def test_discourse_seed_idempotent(db_session):
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    seed_mod = importlib.import_module("seed_api_keys")

    await seed_mod.seed_discourse_api_key(db_session)
    await db_session.commit()

    await seed_mod.seed_discourse_api_key(db_session)
    await db_session.commit()

    from sqlalchemy import text

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM users WHERE username = :username"),
        {"username": DISCOURSE_USERNAME},
    )
    count = result.scalar_one()
    assert count == 1, "idempotent seeding must not duplicate the user"

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM api_keys WHERE name = :name"),
        {"name": "Discourse Adapter (Development)"},
    )
    count = result.scalar_one()
    assert count == 1, "idempotent seeding must not duplicate the API key"


@pytest.mark.asyncio
async def test_discourse_seed_rotates_stale_prefix_on_active_row(db_session):
    """TASK-1462.01: stale key_prefix + stale key_hash on an active row must
    be rotated atomically so the dev plaintext auths via the prefix lookup."""
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
            VALUES (:u, :e, :pw, :n, TRUE, 'agent', '[]'::jsonb, NOW(), NOW())
        """),
        {
            "u": DISCOURSE_USERNAME,
            "e": "discourse-adapter-community-opennotes-ai@opennotes.local",
            "pw": get_password_hash("throwaway"),
            "n": "Discourse Adapter (community.opennotes.ai)",
        },
    )

    user_row = await db_session.execute(
        text("SELECT id FROM users WHERE username = :u"),
        {"u": DISCOURSE_USERNAME},
    )
    user_id = user_row.scalar_one()

    stale_hash = get_password_hash("opk_stale_wrong_discourse_plaintext_to_rotate")
    await db_session.execute(
        text("""
            INSERT INTO api_keys (user_id, name, key_hash, key_prefix, is_active, scopes, created_at)
            VALUES (:user_id, 'Discourse Adapter (Development)', :key_hash,
                    'stale', TRUE, CAST(:scopes AS jsonb), NOW())
        """),
        {
            "user_id": user_id,
            "key_hash": stale_hash,
            "scopes": '["platform:adapter"]',
        },
    )
    await db_session.commit()

    await seed_mod.seed_discourse_api_key(db_session)
    await db_session.commit()

    result = await verify_api_key(db_session, DISCOURSE_DEV_API_KEY)
    assert result is not None, (
        "discourse seed must rotate stale hash + prefix to re-enable dev auth"
    )
    api_key_obj, _ = result
    assert api_key_obj.key_prefix == "discourse", (
        f"key_prefix must be rotated from 'stale' to 'discourse'; got {api_key_obj.key_prefix!r}"
    )
