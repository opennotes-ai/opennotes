"""Unit tests for the seed_api_key return contract (TASK-1462.01).

These tests pin the behavior matrix for `scripts/seed_api_keys.py::seed_api_key`.
The function must return a KeySeedResult so that the prod helpers can gate the
Google Secret Manager push on authentic rotation (not a no-op or scope-only
touch) — otherwise GSM drifts ahead of the DB hash and Cloud Run revisions that
later resolve :latest mount an API key that fails hash verification (the
Discord 401 incident from 2026-04-16).

Each test exercises ONE row of the behavior matrix. We use an in-memory fake
async session that records the SQL it sees, which is enough to tell INSERT
from UPDATE and to recover the parameter dict for the write. We avoid mocking
the function under test entirely.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

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


class _FakeResult:
    def __init__(self, *, first_row=None, scalar=None):
        self._first_row = first_row
        self._scalar = scalar

    def first(self):
        return self._first_row

    def scalar_one(self):
        return self._scalar


class _FakeSession:
    """Async session stand-in that scripts calls through `text()` + params.

    Call `prime_existing_row(...)` to pre-seed what the SELECT on api_keys will
    return. Everything else returns a sentinel scalar.
    """

    def __init__(self):
        self.executed: list[tuple[str, dict]] = []
        self._existing_row: tuple | None = None
        self._next_api_key_id = "fake-api-key-id"

    def prime_existing_row(self, *, api_key_id, is_active, scopes):
        scopes_json = json.dumps(scopes) if scopes is not None else None
        self._existing_row = (api_key_id, is_active, scopes_json)

    async def execute(self, clause, params=None):
        sql = str(clause)
        self.executed.append((sql, dict(params or {})))
        if "FROM api_keys WHERE user_id" in sql and "SELECT" in sql:
            return _FakeResult(first_row=self._existing_row)
        if "INSERT INTO api_keys" in sql:
            return _FakeResult(scalar=self._next_api_key_id)
        return _FakeResult()

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _update_api_keys_hash_call(executed):
    """Return the params of the UPDATE that rewrites key_hash/key_prefix, if any."""
    for sql, params in executed:
        if "UPDATE api_keys" in sql and "key_hash" in sql and "key_prefix" in sql:
            return params
    return None


def _update_scopes_only_call(executed):
    """Return the params of the UPDATE that only touches scopes, if any."""
    for sql, params in executed:
        if "UPDATE api_keys" in sql and "SET scopes" in sql and "key_hash" not in sql:
            return params
    return None


def _insert_api_keys_call(executed):
    for sql, params in executed:
        if "INSERT INTO api_keys" in sql:
            return params
    return None


@pytest.mark.asyncio
async def test_no_op_when_active_row_matches_scopes(seed_module):
    """Active row with matching scopes and force_rotate_active=False is a no-op."""
    session = _FakeSession()
    session.prime_existing_row(
        api_key_id="existing-id",
        is_active=True,
        scopes=["platform:adapter"],
    )

    result = await seed_module.seed_api_key(
        session,
        key_hash="hash-value",
        key_name="Some Key",
        key_prefix="prefix",
        user_id="user-id",
        scopes=["platform:adapter"],
    )

    assert isinstance(result, seed_module.KeySeedResult)
    assert result.status == seed_module.KeySeedStatus.NO_OP
    assert result.hash_written is False
    assert result.should_publish_plaintext is False
    assert _update_api_keys_hash_call(session.executed) is None
    assert _update_scopes_only_call(session.executed) is None
    assert _insert_api_keys_call(session.executed) is None


@pytest.mark.asyncio
async def test_scope_only_update_when_scopes_differ_and_no_force(seed_module):
    """Active row with different scopes and force_rotate_active=False only rewrites scopes."""
    session = _FakeSession()
    session.prime_existing_row(
        api_key_id="existing-id",
        is_active=True,
        scopes=["old:scope"],
    )

    result = await seed_module.seed_api_key(
        session,
        key_hash="hash-value",
        key_name="Some Key",
        key_prefix="prefix",
        user_id="user-id",
        scopes=["platform:adapter"],
    )

    assert result.status == seed_module.KeySeedStatus.SCOPE_ONLY_UPDATED
    assert result.hash_written is False
    assert result.should_publish_plaintext is False
    scope_update = _update_scopes_only_call(session.executed)
    assert scope_update is not None
    assert json.loads(scope_update["scopes"]) == ["platform:adapter"]
    assert _update_api_keys_hash_call(session.executed) is None


@pytest.mark.asyncio
async def test_active_rotated_when_force_rotate_and_matching_scopes(seed_module):
    """Active row with matching scopes and force_rotate_active=True rewrites hash+prefix."""
    session = _FakeSession()
    session.prime_existing_row(
        api_key_id="existing-id",
        is_active=True,
        scopes=["platform:adapter"],
    )

    result = await seed_module.seed_api_key(
        session,
        key_hash="NEW-HASH",
        key_name="Some Key",
        key_prefix="newprefix",
        user_id="user-id",
        scopes=["platform:adapter"],
        force_rotate_active=True,
    )

    assert result.status == seed_module.KeySeedStatus.ACTIVE_ROTATED
    assert result.hash_written is True
    assert result.should_publish_plaintext is True

    hash_update = _update_api_keys_hash_call(session.executed)
    assert hash_update is not None
    assert hash_update["key_hash"] == "NEW-HASH"
    assert hash_update["key_prefix"] == "newprefix"


@pytest.mark.asyncio
async def test_active_rotated_rewrites_scopes_when_force_and_scopes_differ(seed_module):
    """Active row with differing scopes and force_rotate_active=True rewrites hash+prefix+scopes."""
    session = _FakeSession()
    session.prime_existing_row(
        api_key_id="existing-id",
        is_active=True,
        scopes=["old:scope"],
    )

    result = await seed_module.seed_api_key(
        session,
        key_hash="NEW-HASH",
        key_name="Some Key",
        key_prefix="newprefix",
        user_id="user-id",
        scopes=["platform:adapter"],
        force_rotate_active=True,
    )

    assert result.status == seed_module.KeySeedStatus.ACTIVE_ROTATED
    assert result.hash_written is True
    assert result.should_publish_plaintext is True

    hash_update = _update_api_keys_hash_call(session.executed)
    assert hash_update is not None
    assert hash_update["key_hash"] == "NEW-HASH"
    assert hash_update["key_prefix"] == "newprefix"
    assert json.loads(hash_update["scopes"]) == ["platform:adapter"]


@pytest.mark.asyncio
async def test_reactivated_when_existing_row_is_inactive(seed_module):
    """Inactive row is reactivated with new hash+prefix+scopes regardless of force flag."""
    session = _FakeSession()
    session.prime_existing_row(
        api_key_id="existing-id",
        is_active=False,
        scopes=["platform:adapter"],
    )

    result = await seed_module.seed_api_key(
        session,
        key_hash="NEW-HASH",
        key_name="Some Key",
        key_prefix="newprefix",
        user_id="user-id",
        scopes=["platform:adapter"],
    )

    assert result.status == seed_module.KeySeedStatus.REACTIVATED
    assert result.hash_written is True
    assert result.should_publish_plaintext is True

    hash_update = _update_api_keys_hash_call(session.executed)
    assert hash_update is not None
    assert hash_update["key_hash"] == "NEW-HASH"
    assert hash_update["key_prefix"] == "newprefix"


@pytest.mark.asyncio
async def test_created_when_no_existing_row(seed_module):
    """Absent row produces an INSERT and CREATED status."""
    session = _FakeSession()
    # no prime_existing_row() call => SELECT returns None

    result = await seed_module.seed_api_key(
        session,
        key_hash="fresh-hash",
        key_name="Fresh Key",
        key_prefix="freshprefix",
        user_id="user-id",
        scopes=["platform:adapter"],
    )

    assert result.status == seed_module.KeySeedStatus.CREATED
    assert result.hash_written is True
    assert result.should_publish_plaintext is True

    insert = _insert_api_keys_call(session.executed)
    assert insert is not None
    assert insert["key_hash"] == "fresh-hash"
    assert insert["key_prefix"] == "freshprefix"


@pytest.mark.asyncio
async def test_no_commit_inside_seed_api_key(seed_module):
    """seed_api_key must not call db.commit() — callers own the transaction boundary."""

    class AssertNoCommitSession(_FakeSession):
        async def commit(self):
            raise AssertionError("seed_api_key must not commit; callers own commit")

    session = AssertNoCommitSession()
    session.prime_existing_row(
        api_key_id="existing-id",
        is_active=True,
        scopes=["platform:adapter"],
    )

    result = await seed_module.seed_api_key(
        session,
        key_hash="hash-value",
        key_name="Some Key",
        key_prefix="prefix",
        user_id="user-id",
        scopes=["platform:adapter"],
    )

    assert result.status == seed_module.KeySeedStatus.NO_OP


@pytest.mark.asyncio
async def test_key_seed_result_is_frozen_dataclass(seed_module):
    """KeySeedResult must be frozen so callers cannot mutate status mid-flow."""
    r = seed_module.KeySeedResult(
        status=seed_module.KeySeedStatus.NO_OP,
        hash_written=False,
        should_publish_plaintext=False,
    )
    with pytest.raises((AttributeError, Exception)):
        r.hash_written = True  # type: ignore[misc]


@pytest.mark.asyncio
async def test_force_rotate_active_is_keyword_only(seed_module):
    """force_rotate_active must be keyword-only so existing positional callers are unchanged."""
    import inspect

    sig = inspect.signature(seed_module.seed_api_key)
    param = sig.parameters.get("force_rotate_active")
    assert param is not None, "seed_api_key must accept force_rotate_active"
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
    assert param.default is False
