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


class _AsyncCommitSession:
    """Minimal async-session stand-in: supports `await db.commit()`/`rollback()`."""

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


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
        await seed_module._seed_and_save_prod_platform_key(db=_AsyncCommitSession())

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
        await seed_module._seed_and_save_prod_platform_key(db=_AsyncCommitSession())

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
        await seed_module._seed_and_save_prod_playground_key(db=_AsyncCommitSession())

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
        await seed_module._seed_and_save_prod_key(db=_AsyncCommitSession())

    fake_client.add_secret_version.assert_called_once()
    _, kwargs = fake_client.add_secret_version.call_args
    assert kwargs["parent"] == "projects/open-notes-core/secrets/opennotes-api-key"
    assert kwargs["payload"] == {"data": known_key.encode()}

    captured = capsys.readouterr()
    assert known_key not in captured.out
    assert known_key not in captured.err


@pytest.mark.asyncio
async def test_prod_main_sets_tracebacklimit_to_zero(seed_module, monkeypatch):
    """TASK-1422.13.05.01: prod main flow must set sys.tracebacklimit to 0
    before any key is minted, so a secondary uncaught exception cannot print
    a traceback with local reprs to stderr.
    """
    import sys as real_sys

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("OPENNOTES_API_KEY", raising=False)
    monkeypatch.delenv("PLAYGROUND_API_KEY", raising=False)
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)

    observed: dict[str, object] = {}

    async def record_tracebacklimit(db):
        observed["tracebacklimit"] = getattr(real_sys, "tracebacklimit", "<unset>")

    monkeypatch.setattr(seed_module, "_seed_and_save_prod_key", record_tracebacklimit)
    monkeypatch.setattr(seed_module, "_seed_and_save_prod_playground_key", record_tracebacklimit)
    monkeypatch.setattr(seed_module, "_seed_and_save_prod_platform_key", record_tracebacklimit)

    class DummyResult:
        def scalar_one(self):
            return 0

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, *args, **kwargs):
            return DummyResult()

        async def commit(self):
            return None

        async def rollback(self):
            return None

    class DummySessionFactory:
        def __call__(self, *args, **kwargs):
            return DummySession()

    monkeypatch.setattr(seed_module, "AsyncSession", DummySessionFactory())
    monkeypatch.setattr(seed_module, "get_engine", lambda: None)

    prior_limit = getattr(real_sys, "tracebacklimit", None)
    try:
        await seed_module.main()
    finally:
        if prior_limit is None and hasattr(real_sys, "tracebacklimit"):
            del real_sys.tracebacklimit
        elif prior_limit is not None:
            real_sys.tracebacklimit = prior_limit

    assert observed["tracebacklimit"] == 0, (
        f"sys.tracebacklimit should be 0 during prod seeding; observed {observed['tracebacklimit']!r}"
    )


@pytest.mark.asyncio
async def test_exception_handler_does_not_leak_plaintext_via_primary_exception(
    seed_module, monkeypatch, capsys
):
    """TASK-1422.13.05.01: when a primary exception carries the plaintext in
    its message, the outer handler's `str(e)` must not echo the plaintext to
    stdout or stderr.
    """
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("OPENNOTES_API_KEY", raising=False)
    monkeypatch.delenv("PLAYGROUND_API_KEY", raising=False)
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)

    sentinel_plaintext = "opk_LEAKPRIM_sentinel_primary_exception_value"

    async def raise_primary_with_plaintext(db):
        raise RuntimeError(f"synthetic failure containing {sentinel_plaintext}")

    monkeypatch.setattr(seed_module, "_seed_and_save_prod_key", raise_primary_with_plaintext)

    class DummyResult:
        def scalar_one(self):
            return 0

    class RollbackSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, *args, **kwargs):
            return DummyResult()

        async def commit(self):
            return None

        async def rollback(self):
            return None

    class RollbackFactory:
        def __call__(self, *args, **kwargs):
            return RollbackSession()

    monkeypatch.setattr(seed_module, "AsyncSession", RollbackFactory())
    monkeypatch.setattr(seed_module, "get_engine", lambda: None)

    with pytest.raises(SystemExit):
        await seed_module.main()

    captured = capsys.readouterr()
    assert sentinel_plaintext not in captured.out, f"plaintext leaked to stdout: {captured.out!r}"
    assert sentinel_plaintext not in captured.err, f"plaintext leaked to stderr: {captured.err!r}"


@pytest.mark.asyncio
async def test_commit_happens_before_gsm_push(seed_module, monkeypatch):
    """TASK-1422.13.05.02: DB commit must precede the GSM push so a DB rollback
    cannot orphan a fresh GSM version.
    """
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)

    async def fake_get_or_create(db):
        return "user-uuid"

    async def fake_seed(db, key_hash, name, key_prefix, **kwargs):
        return None

    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)
    monkeypatch.setattr(seed_module, "seed_api_key", fake_seed)
    monkeypatch.setattr(
        seed_module,
        "generate_api_key",
        lambda: ("opk_ORDER_sentinel_plaintext_value", "ORDER"),
    )

    call_order: list[str] = []

    class OrderingSession:
        async def commit(self):
            call_order.append("commit")

        async def rollback(self):
            call_order.append("rollback")

    fake_client = MagicMock()
    fake_client.add_secret_version.side_effect = lambda *a, **k: call_order.append("gsm_push")

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_platform_key(db=OrderingSession())

    assert call_order == ["commit", "gsm_push"], (
        f"commit must precede GSM push, got order: {call_order}"
    )


@pytest.mark.asyncio
async def test_commit_failure_midway_skips_all_subsequent_gsm_pushes(seed_module, monkeypatch):
    """TASK-1422.13.05.02: if the DB commit fails for key #2, no GSM version
    is added for key #2 or key #3. Only key #1 should already be on GSM.
    """
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("OPENNOTES_API_KEY", raising=False)
    monkeypatch.delenv("PLAYGROUND_API_KEY", raising=False)
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)

    async def fake_get_or_create(db):
        return "user-uuid"

    async def fake_seed(db, key_hash, name, key_prefix=None, **kwargs):
        return None

    monkeypatch.setattr(seed_module, "get_or_create_service_user", fake_get_or_create)
    monkeypatch.setattr(seed_module, "get_or_create_playground_user", fake_get_or_create)
    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)
    monkeypatch.setattr(seed_module, "seed_api_key", fake_seed)

    mint_counter = {"n": 0}

    def fake_generate():
        mint_counter["n"] += 1
        return (
            f"opk_MINT{mint_counter['n']:03d}_sentinel_plaintext",
            f"MINT{mint_counter['n']:03d}",
        )

    monkeypatch.setattr(seed_module, "generate_api_key", fake_generate)

    class FailingSession:
        def __init__(self):
            self.commit_calls = 0

        async def commit(self):
            self.commit_calls += 1
            if self.commit_calls == 2:
                raise RuntimeError("simulated DB commit failure on second key")

        async def rollback(self):
            return None

    session = FailingSession()
    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_key(db=session)
        with pytest.raises(RuntimeError, match="simulated DB commit failure"):
            await seed_module._seed_and_save_prod_playground_key(db=session)

    assert fake_client.add_secret_version.call_count == 1, (
        "only the first key's GSM version should have been pushed"
    )
    _, kwargs = fake_client.add_secret_version.call_args
    assert kwargs["parent"].endswith("opennotes-api-key")
