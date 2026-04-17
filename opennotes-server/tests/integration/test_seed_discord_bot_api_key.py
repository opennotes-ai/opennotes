import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from src.users.crud import verify_api_key

DEV_API_KEY = "XcvlCe7ewY4z4VzbWeogvkJZA-5hxY_xJn5PJmZJN0c"
DISCORD_BOT_SCOPES = ["platform:adapter"]


def _load_seed_module():
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module("seed_api_keys")


@pytest.mark.asyncio
async def test_discord_bot_service_account_created_with_correct_flags(db_session):
    seed_mod = _load_seed_module()

    await seed_mod.seed_dev_api_key(db_session)
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT principal_type, platform_roles FROM users WHERE username = :username"),
        {"username": "discord-bot-service"},
    )
    row = result.first()

    assert row is not None, "discord-bot-service user must exist after seeding"
    principal_type, platform_roles = row
    assert principal_type == "system", "discord-bot-service must be a system principal"
    assert "platform_admin" in platform_roles, (
        "discord-bot-service must have platform_admin role (required for future /admin/api-keys mint)"
    )


@pytest.mark.asyncio
async def test_discord_bot_key_has_platform_adapter_scope(db_session):
    seed_mod = _load_seed_module()

    await seed_mod.seed_dev_api_key(db_session)
    await db_session.commit()

    result = await verify_api_key(db_session, DEV_API_KEY)
    assert result is not None, "discord-bot dev API key must authenticate"

    api_key_obj, authenticated_user = result
    assert authenticated_user.username == "discord-bot-service"
    assert api_key_obj.is_active is True
    assert api_key_obj.scopes == DISCORD_BOT_SCOPES


@pytest.mark.asyncio
async def test_discord_bot_seed_idempotent(db_session):
    seed_mod = _load_seed_module()

    await seed_mod.seed_dev_api_key(db_session)
    await db_session.commit()

    await seed_mod.seed_dev_api_key(db_session)
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM users WHERE username = :username"),
        {"username": "discord-bot-service"},
    )
    count = result.scalar_one()
    assert count == 1, "idempotent seeding must not duplicate the user"

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM api_keys WHERE name = :name"),
        {"name": "Discord Bot (Development)"},
    )
    count = result.scalar_one()
    assert count == 1, "idempotent seeding must not duplicate the API key"


@pytest.mark.asyncio
async def test_discord_bot_seed_patches_missing_platform_admin(db_session):
    """Regression guard: if a pre-existing discord-bot-service row is missing
    platform_admin in platform_roles, re-running the seed must patch it.
    This is the exact scenario that triggered TASK-1456 in prod."""
    seed_mod = _load_seed_module()

    from src.auth.password import get_password_hash

    await db_session.execute(
        text("""
            INSERT INTO users (username, email, hashed_password, full_name,
                               is_active, principal_type, platform_roles,
                               created_at, updated_at)
            VALUES ('discord-bot-service', 'discord-bot@opennotes.local',
                    :pw, 'Discord Bot Service Account',
                    TRUE, 'agent', '[]'::json,
                    NOW(), NOW())
        """),
        {"pw": get_password_hash("throwaway")},
    )
    await db_session.commit()

    await seed_mod.seed_dev_api_key(db_session)
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT principal_type, platform_roles FROM users WHERE username = :username"),
        {"username": "discord-bot-service"},
    )
    principal_type, platform_roles = result.first()
    assert principal_type == "system", "seed must patch principal_type to system"
    assert "platform_admin" in platform_roles, (
        "seed must patch platform_roles to include platform_admin"
    )
