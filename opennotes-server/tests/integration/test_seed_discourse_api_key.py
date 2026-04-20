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
