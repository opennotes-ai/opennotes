"""Unit tests for seed_api_keys GSM push behavior (TASK-1422.13.05, TASK-1462.01).

Covers the production paths in scripts/seed_api_keys.py that push minted
plaintext API keys to Google Secret Manager after the DB hash is committed.

Invariants under test:
- Prod path with minted key on a FRESH row (CREATED): add_secret_version is
  called with the correct parent path and plaintext payload bytes.
- Prod path with env override: add_secret_version is NOT called regardless
  of the DB state — the operator owns the plaintext in GSM.
- Prod path with pre-existing active row + minted key: force_rotate_active
  is False in this branch, so there is NO rotation and NO GSM push (this is
  the bug TASK-1462.01 fixed — before the fix, GSM was pushed unconditionally
  and the DB hash drifted behind GSM, breaking auth).
- Plaintext never appears on stdout in the production path.
- Missing secret shell surfaces a clear operator-facing error.
"""

from __future__ import annotations

import importlib
import json
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


class _FakeResult:
    def __init__(self, *, first_row=None, scalar=None):
        self._first_row = first_row
        self._scalar = scalar

    def first(self):
        return self._first_row

    def scalar_one(self):
        return self._scalar


class _SeedDBFakeSession:
    """Async session fake that records SQL it sees and returns prepared rows.

    Scoped narrowly to the queries `seed_api_key` + helpers issue:
    - SELECT on api_keys returns a pre-primed row (or None for CREATED path).
    - INSERT on api_keys returns a sentinel scalar id.
    - Any other SELECT (users table lookups) returns an empty result — tests
      that need users pre-seed by patching `get_or_create_*` helpers.
    """

    def __init__(self):
        self.executed: list[tuple[str, dict]] = []
        self._existing_row: tuple | None = None
        self.commit_calls = 0
        self.commit_side_effect = None

    def prime_existing_row(self, *, api_key_id, is_active, scopes):
        scopes_json = json.dumps(scopes) if scopes is not None else None
        self._existing_row = (api_key_id, is_active, scopes_json)

    async def execute(self, clause, params=None):
        sql = str(clause)
        self.executed.append((sql, dict(params or {})))
        if "FROM api_keys WHERE user_id" in sql and "SELECT" in sql:
            return _FakeResult(first_row=self._existing_row)
        if "INSERT INTO api_keys" in sql:
            return _FakeResult(scalar="fresh-id")
        return _FakeResult()

    async def commit(self):
        self.commit_calls += 1
        if self.commit_side_effect is not None:
            self.commit_side_effect(self.commit_calls)

    async def rollback(self):
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
async def test_prod_platform_key_pushes_to_gsm_when_creating_fresh_row(
    seed_module, monkeypatch, capsys
):
    """Fresh DB: prod helper mints a key, INSERTs, commits, pushes to GSM."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)

    async def fake_get_or_create(db):
        return "user-uuid"

    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)

    known_key = "opk_DEADBEEF_not_a_real_secret_plaintext_sentinel"
    monkeypatch.setattr(seed_module, "generate_api_key", lambda: (known_key, "DEADBEEF"))

    session = _SeedDBFakeSession()  # no existing row => CREATED path
    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_platform_key(db=session)

    fake_client.add_secret_version.assert_called_once()
    _, kwargs = fake_client.add_secret_version.call_args
    assert kwargs["parent"] == "projects/open-notes-core/secrets/platform-api-key"
    assert kwargs["payload"] == {"data": known_key.encode()}

    captured = capsys.readouterr()
    assert known_key not in captured.out
    assert known_key not in captured.err


@pytest.mark.asyncio
async def test_prod_platform_key_env_override_skips_gsm_push(seed_module, monkeypatch, capsys):
    """Env-override branch: operator already pushed plaintext to GSM out-of-band
    (SOPS + add-version), so seed job must never re-push. This must hold even
    when the DB is fresh and we INSERT a CREATED row — the operator owns GSM.
    """
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    override_key = "opk_override_env_supplied_platform_api_key_value"
    monkeypatch.setenv("PLATFORM_API_KEY", override_key)

    async def fake_get_or_create(db):
        return "user-uuid"

    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)

    session = _SeedDBFakeSession()
    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_platform_key(db=session)

    fake_client.add_secret_version.assert_not_called()

    captured = capsys.readouterr()
    assert override_key not in captured.out
    assert override_key not in captured.err


@pytest.mark.asyncio
async def test_prod_platform_key_active_row_no_override_is_no_op(seed_module, monkeypatch, capsys):
    """Regression: when an active row with matching scopes exists and the
    operator did NOT provide an env override, the prod helper must NOT push
    to GSM (would drift the GSM plaintext ahead of the unchanged DB hash).
    This is the exact bug that caused the 2026-04-16 Discord 401 incident.
    """
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)

    async def fake_get_or_create(db):
        return "user-uuid"

    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)
    known_key = "opk_MINTED01_fresh_plaintext_but_db_has_old_hash"
    monkeypatch.setattr(seed_module, "generate_api_key", lambda: (known_key, "MINTED01"))

    session = _SeedDBFakeSession()
    session.prime_existing_row(
        api_key_id="existing-id", is_active=True, scopes=["platform-admin:update"]
    )

    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_platform_key(db=session)

    fake_client.add_secret_version.assert_not_called()


@pytest.mark.asyncio
async def test_prod_platform_key_active_rotate_on_override_rewrites_hash_and_prefix(
    seed_module, monkeypatch
):
    """When operator provides an env override on an already-active row,
    force_rotate_active=True flows through and the UPDATE must touch BOTH
    key_hash AND key_prefix so verify_api_key's prefix-based lookup lands on
    the correct row.
    """
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    override_key = "opk_NEWPREFIX_override_plaintext_rotated_by_operator"
    monkeypatch.setenv("PLATFORM_API_KEY", override_key)

    async def fake_get_or_create(db):
        return "user-uuid"

    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)

    session = _SeedDBFakeSession()
    session.prime_existing_row(
        api_key_id="existing-id",
        is_active=True,
        scopes=["platform-admin:update"],
    )

    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_platform_key(db=session)

    # No GSM push: operator owns plaintext.
    fake_client.add_secret_version.assert_not_called()

    # UPDATE api_keys must have been issued with BOTH key_hash AND key_prefix.
    hash_update = next(
        (
            params
            for sql, params in session.executed
            if "UPDATE api_keys" in sql and "key_hash" in sql and "key_prefix" in sql
        ),
        None,
    )
    assert hash_update is not None, "active-rotate path must UPDATE key_hash + key_prefix"
    assert hash_update["key_prefix"] == "NEWPREFIX"


@pytest.mark.asyncio
async def test_prod_playground_key_pushes_to_gsm_when_creating_fresh_row(
    seed_module, monkeypatch, capsys
):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("PLAYGROUND_API_KEY", raising=False)

    async def fake_get_or_create(db):
        return "user-uuid"

    monkeypatch.setattr(seed_module, "get_or_create_playground_user", fake_get_or_create)

    known_key = "opk_PLAYGR0UND_sentinel_secret_plaintext"
    monkeypatch.setattr(seed_module, "generate_api_key", lambda: (known_key, "PLAYGR0UND"))

    session = _SeedDBFakeSession()
    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_playground_key(db=session)

    fake_client.add_secret_version.assert_called_once()
    _, kwargs = fake_client.add_secret_version.call_args
    assert kwargs["parent"] == "projects/open-notes-core/secrets/playground-api-key"
    assert kwargs["payload"] == {"data": known_key.encode()}

    captured = capsys.readouterr()
    assert known_key not in captured.out
    assert known_key not in captured.err


@pytest.mark.asyncio
async def test_prod_opennotes_key_pushes_to_gsm_when_creating_fresh_row(
    seed_module, monkeypatch, capsys
):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("OPENNOTES_API_KEY", raising=False)

    async def fake_get_or_create(db):
        return "user-uuid"

    monkeypatch.setattr(seed_module, "get_or_create_service_user", fake_get_or_create)

    known_key = "opk_DISCORD00_sentinel_secret_plaintext"
    monkeypatch.setattr(seed_module, "generate_api_key", lambda: (known_key, "DISCORD00"))

    session = _SeedDBFakeSession()
    fake_client = MagicMock()

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_key(db=session)

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
    monkeypatch.delenv("DISCOURSE_OPENNOTES_API_KEY", raising=False)

    observed: dict[str, object] = {}

    async def record_tracebacklimit(db):
        observed["tracebacklimit"] = getattr(real_sys, "tracebacklimit", "<unset>")

    monkeypatch.setattr(seed_module, "_seed_and_save_prod_key", record_tracebacklimit)
    monkeypatch.setattr(seed_module, "_seed_and_save_prod_playground_key", record_tracebacklimit)
    monkeypatch.setattr(seed_module, "_seed_and_save_prod_platform_key", record_tracebacklimit)
    monkeypatch.setattr(seed_module, "_seed_and_save_prod_discourse_key", record_tracebacklimit)

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

    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)
    monkeypatch.setattr(
        seed_module,
        "generate_api_key",
        lambda: ("opk_ORDER_sentinel_plaintext_value", "ORDER"),
    )

    call_order: list[str] = []

    class OrderingSession(_SeedDBFakeSession):
        async def commit(self):
            await super().commit()
            call_order.append("commit")

    session = OrderingSession()  # fresh row => CREATED => push
    fake_client = MagicMock()
    fake_client.add_secret_version.side_effect = lambda *a, **k: call_order.append("gsm_push")

    with patch(
        "google.cloud.secretmanager.SecretManagerServiceClient",
        return_value=fake_client,
    ):
        await seed_module._seed_and_save_prod_platform_key(db=session)

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

    monkeypatch.setattr(seed_module, "get_or_create_service_user", fake_get_or_create)
    monkeypatch.setattr(seed_module, "get_or_create_playground_user", fake_get_or_create)
    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)

    mint_counter = {"n": 0}

    def fake_generate():
        mint_counter["n"] += 1
        return (
            f"opk_MINT{mint_counter['n']:03d}_sentinel_plaintext",
            f"MINT{mint_counter['n']:03d}",
        )

    monkeypatch.setattr(seed_module, "generate_api_key", fake_generate)

    session = _SeedDBFakeSession()

    def fail_on_second_commit(call_n):
        if call_n == 2:
            raise RuntimeError("simulated DB commit failure on second key")

    session.commit_side_effect = fail_on_second_commit
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


@pytest.mark.asyncio
async def test_gsm_push_raises_after_commit_does_not_rollback_db(seed_module, monkeypatch):
    """TASK-1462.01: when the GSM push raises AFTER the DB commit has landed,
    the exception propagates (operator must recover manually) and the
    DB-side seed is already durable — we do not attempt a rollback that would
    desynchronize the state further.
    """
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "open-notes-core")
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)

    async def fake_get_or_create(db):
        return "user-uuid"

    monkeypatch.setattr(seed_module, "get_or_create_platform_user", fake_get_or_create)
    monkeypatch.setattr(
        seed_module,
        "generate_api_key",
        lambda: ("opk_POSTCOMMIT_plaintext", "POSTCOMMIT"),
    )

    session = _SeedDBFakeSession()  # fresh => CREATED => push
    fake_client = MagicMock()
    fake_client.add_secret_version.side_effect = RuntimeError("gsm transport failure")

    with (
        patch(
            "google.cloud.secretmanager.SecretManagerServiceClient",
            return_value=fake_client,
        ),
        pytest.raises(RuntimeError, match="gsm transport failure"),
    ):
        await seed_module._seed_and_save_prod_platform_key(db=session)

    assert session.commit_calls == 1, "commit must have landed before the GSM push failed"
