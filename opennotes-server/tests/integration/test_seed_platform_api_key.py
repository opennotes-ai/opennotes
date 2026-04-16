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
        text(
            "SELECT principal_type, platform_roles FROM users WHERE username = :username"
        ),
        {"username": "platform-service"},
    )
    row = result.first()

    assert row is not None, "platform-service user must exist after seeding"
    principal_type, platform_roles = row
    assert principal_type == "system", "platform-service must be a system principal"
    assert "platform_admin" in platform_roles, (
        "platform-service must have platform_admin role"
    )


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
