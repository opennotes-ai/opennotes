import pytest

from src.auth.password import get_password_hash
from src.users.crud import verify_api_key
from src.users.models import APIKey, User

PLAYGROUND_DEV_API_KEY = "opk_playground_dev_readonly_access_key_2024"
PLAYGROUND_SCOPES = ["simulations:read"]


@pytest.mark.asyncio
async def test_playground_key_with_correct_prefix_authenticates(db_session):
    user = User(
        username="playground-service",
        email="playground@opennotes.local",
        hashed_password=get_password_hash("unused"),
        is_active=True,
        is_service_account=False,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    api_key = APIKey(
        user_id=user.id,
        name="Playground (Development)",
        key_hash=get_password_hash(PLAYGROUND_DEV_API_KEY),
        key_prefix="playground",
        is_active=True,
        scopes=PLAYGROUND_SCOPES,
    )
    db_session.add(api_key)
    await db_session.commit()

    result = await verify_api_key(db_session, PLAYGROUND_DEV_API_KEY)

    assert result is not None, (
        "verify_api_key must authenticate the playground dev API key "
        "when key_prefix='playground' is set"
    )
    api_key_obj, authenticated_user = result
    assert authenticated_user.username == "playground-service"
    assert api_key_obj.is_active is True


@pytest.mark.asyncio
async def test_playground_key_without_prefix_fails_authentication(db_session):
    user = User(
        username="playground-service-no-prefix",
        email="playground-no-prefix@opennotes.local",
        hashed_password=get_password_hash("unused"),
        is_active=True,
        is_service_account=False,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    api_key = APIKey(
        user_id=user.id,
        name="Playground (Development) - No Prefix",
        key_hash=get_password_hash(PLAYGROUND_DEV_API_KEY),
        key_prefix=None,
        is_active=True,
        scopes=PLAYGROUND_SCOPES,
    )
    db_session.add(api_key)
    await db_session.commit()

    result = await verify_api_key(db_session, PLAYGROUND_DEV_API_KEY)

    assert result is None, (
        "verify_api_key should FAIL when key_prefix is NULL because "
        "the opk_ prefix routes through the prefix-based O(1) lookup "
        "which queries key_prefix='playground', not key_prefix IS NULL"
    )


@pytest.mark.asyncio
async def test_seed_playground_api_key_passes_key_prefix(db_session):
    import importlib
    import sys
    from pathlib import Path

    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    seed_mod = importlib.import_module("seed_api_keys")

    parts = seed_mod.PLAYGROUND_DEV_API_KEY.split("_", 2)
    expected_prefix = parts[1]
    assert expected_prefix == "playground"

    import ast
    import inspect

    source = inspect.getsource(seed_mod.seed_playground_api_key)
    tree = ast.parse(source)

    found_key_prefix_arg = False
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "key_prefix":
            found_key_prefix_arg = True

    assert found_key_prefix_arg, "seed_playground_api_key must pass key_prefix to seed_api_key"
