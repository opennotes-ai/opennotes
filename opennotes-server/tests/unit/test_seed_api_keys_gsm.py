"""Unit tests for seed_api_keys GSM push behavior (TASK-1422.13.05).

Covers the production paths in scripts/seed_api_keys.py that push minted
plaintext API keys to Google Secret Manager after the DB hash is committed.

Invariants under test:
- Prod path with minted key: add_secret_version is called with the correct
  parent path and plaintext payload bytes.
- Prod path with env override (idempotency): add_secret_version is NOT called.
- Plaintext never appears on stdout in the production path.
- Missing secret shell surfaces a clear operator-facing error.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def seed_module():
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    if "seed_api_keys" in sys.modules:
        del sys.modules["seed_api_keys"]
    module = importlib.import_module("seed_api_keys")
    yield module
    if "seed_api_keys" in sys.modules:
        del sys.modules["seed_api_keys"]


def test_push_plaintext_to_gsm_calls_add_secret_version(seed_module, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")

    fake_client = MagicMock()
    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        seed_module._push_plaintext_to_gsm("platform-api-key", "opk_abc_secret")

    fake_client.add_secret_version.assert_called_once()
    _, kwargs = fake_client.add_secret_version.call_args
    assert kwargs["parent"] == "projects/open-notes-core/secrets/platform-api-key"
    assert kwargs["payload"] == {"data": b"opk_abc_secret"}


def test_push_plaintext_to_gsm_missing_shell_raises_operator_error(seed_module, monkeypatch):
    from google.api_core import exceptions as gax_exceptions

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")

    fake_client = MagicMock()
    fake_client.add_secret_version.side_effect = gax_exceptions.NotFound(
        "Secret [platform-api-key] not found"
    )

    with (
        patch(
            "google.cloud.secretmanager.SecretManagerServiceClient",
            return_value=fake_client,
        ),
        pytest.raises(RuntimeError, match=r"tofu apply|infra apply|infrastructure"),
    ):
        seed_module._push_plaintext_to_gsm("platform-api-key", "opk_abc_secret")


def test_push_plaintext_requires_project_id(seed_module, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)

    with pytest.raises(RuntimeError, match=r"GOOGLE_CLOUD_PROJECT|GCP_PROJECT_ID"):
        seed_module._push_plaintext_to_gsm("platform-api-key", "opk_abc_secret")


@pytest.mark.asyncio
async def test_prod_platform_key_pushes_to_gsm_and_no_plaintext_on_stdout(
    seed_module, monkeypatch, capsys
):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)

    async def fake_get_or_create(db):
        return "user-uuid"

    async def fake_seed(db, key_hash, name, key_prefix, **kwargs):
        return None

    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)
    monkeypatch.setattr(seed_module, "seed_api_key", fake_seed)

    known_key = "opk_DEADBEEF_not_a_real_secret_plaintext_sentinel"
    monkeypatch.setattr(seed_module, "generate_api_key", lambda: (known_key, "DEADBEEF"))

    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_platform_key(db=MagicMock())

    fake_client.add_secret_version.assert_called_once()
    _, kwargs = fake_client.add_secret_version.call_args
    assert kwargs["parent"] == "projects/open-notes-core/secrets/platform-api-key"
    assert kwargs["payload"] == {"data": known_key.encode()}

    captured = capsys.readouterr()
    assert known_key not in captured.out
    assert known_key not in captured.err

    assert not Path("/tmp/platform-api-key.txt").exists() or (
        known_key
        not in Path("/tmp/platform-api-key.txt").read_text(encoding="utf-8", errors="ignore")
    )


@pytest.mark.asyncio
async def test_prod_platform_key_env_override_skips_gsm_push(seed_module, monkeypatch, capsys):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    override_key = "opk_override_env_supplied_platform_api_key_value"
    monkeypatch.setenv("PLATFORM_API_KEY", override_key)

    async def fake_get_or_create(db):
        return "user-uuid"

    async def fake_seed(db, key_hash, name, key_prefix, **kwargs):
        return None

    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)
    monkeypatch.setattr(seed_module, "seed_api_key", fake_seed)

    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_platform_key(db=MagicMock())

    fake_client.add_secret_version.assert_not_called()

    captured = capsys.readouterr()
    assert override_key not in captured.out
    assert override_key not in captured.err


@pytest.mark.asyncio
async def test_prod_playground_key_pushes_to_gsm(seed_module, monkeypatch, capsys):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("PLAYGROUND_API_KEY", raising=False)

    async def fake_get_or_create(db):
        return "user-uuid"

    async def fake_seed(db, key_hash, name, key_prefix, **kwargs):
        return None

    monkeypatch.setattr(seed_module, "get_or_create_playground_user", fake_get_or_create)
    monkeypatch.setattr(seed_module, "seed_api_key", fake_seed)

    known_key = "opk_PLAYGR0UND_sentinel_secret_plaintext"
    monkeypatch.setattr(seed_module, "generate_api_key", lambda: (known_key, "PLAYGR0UND"))

    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_playground_key(db=MagicMock())

    fake_client.add_secret_version.assert_called_once()
    _, kwargs = fake_client.add_secret_version.call_args
    assert kwargs["parent"] == "projects/open-notes-core/secrets/playground-api-key"
    assert kwargs["payload"] == {"data": known_key.encode()}

    captured = capsys.readouterr()
    assert known_key not in captured.out
    assert known_key not in captured.err


@pytest.mark.asyncio
async def test_prod_opennotes_key_pushes_to_gsm(seed_module, monkeypatch, capsys):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("OPENNOTES_API_KEY", raising=False)

    async def fake_get_or_create(db):
        return "user-uuid"

    async def fake_seed(db, key_hash, name, key_prefix=None, **kwargs):
        return None

    monkeypatch.setattr(seed_module, "get_or_create_service_user", fake_get_or_create)
    monkeypatch.setattr(seed_module, "seed_api_key", fake_seed)

    known_key = "opk_DISCORD00_sentinel_secret_plaintext"
    monkeypatch.setattr(seed_module, "generate_api_key", lambda: (known_key, "DISCORD00"))

    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_key(db=MagicMock())

    fake_client.add_secret_version.assert_called_once()
    _, kwargs = fake_client.add_secret_version.call_args
    assert kwargs["parent"] == "projects/open-notes-core/secrets/opennotes-api-key"
    assert kwargs["payload"] == {"data": known_key.encode()}

    captured = capsys.readouterr()
    assert known_key not in captured.out
    assert known_key not in captured.err
