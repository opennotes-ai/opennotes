import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _load_seed_module():
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module("seed_api_keys")


@pytest.mark.asyncio
async def test_seed_vibecheck_api_key_uses_expected_scope_and_prefix():
    seed_mod = _load_seed_module()
    db = AsyncMock()
    user_id = uuid4()

    with (
        patch.object(seed_mod, "get_or_create_vibecheck_user", new=AsyncMock(return_value=user_id)),
        patch.object(seed_mod, "get_password_hash", return_value="hashed-key"),
        patch.object(seed_mod, "seed_api_key", new=AsyncMock()) as mock_seed_api_key,
    ):
        await seed_mod.seed_vibecheck_api_key(db)

    mock_seed_api_key.assert_awaited_once_with(
        db,
        "hashed-key",
        seed_mod.VIBECHECK_API_KEY_NAME,
        key_prefix="vibecheck",
        user_id=user_id,
        scopes=seed_mod.VIBECHECK_SCOPES,
        force_rotate_active=True,
    )


@pytest.mark.asyncio
async def test_prod_vibecheck_seed_honors_override_without_gsm_push(monkeypatch):
    seed_mod = _load_seed_module()
    db = AsyncMock()
    user_id = uuid4()
    override_key = "opk_vibecheck_override_secret"

    monkeypatch.setenv("OPENNOTES_VIBECHECK_API_KEY", override_key)

    with (
        patch.object(seed_mod, "get_or_create_vibecheck_user", new=AsyncMock(return_value=user_id)),
        patch.object(seed_mod, "get_password_hash", return_value="hashed-override"),
        patch.object(
            seed_mod,
            "seed_api_key",
            new=AsyncMock(
                return_value=seed_mod.KeySeedResult(
                    status=seed_mod.KeySeedStatus.ACTIVE_ROTATED,
                    hash_written=True,
                    should_publish_plaintext=True,
                )
            ),
        ) as mock_seed_api_key,
        patch.object(seed_mod, "_push_plaintext_to_gsm") as mock_push,
    ):
        await seed_mod._seed_and_save_prod_vibecheck_key(db)

    mock_seed_api_key.assert_awaited_once_with(
        db,
        "hashed-override",
        seed_mod.PROD_VIBECHECK_API_KEY_NAME,
        "vibecheck",
        user_id=user_id,
        scopes=seed_mod.VIBECHECK_SCOPES,
        force_rotate_active=True,
    )
    db.commit.assert_awaited_once()
    mock_push.assert_not_called()
