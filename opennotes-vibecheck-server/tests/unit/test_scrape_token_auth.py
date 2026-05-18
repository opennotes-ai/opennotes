"""Unit tests for DB-backed scrape token authentication (TASK-1651.03).

Tests exercise require_scrape_token against a fake asyncpg pool so no
real database is needed. All 401 failure paths produce the same
{"detail": "invalid_token"} response body so callers cannot distinguish
unknown-prefix from wrong-hash from expired.
"""
from __future__ import annotations

import datetime
import hashlib
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException

from src.auth.scrape_token import require_scrape_token
from src.config import Settings


def _make_token(prefix: str, secret: str) -> str:
    return f"opk_{prefix}_{secret}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _make_row(
    *,
    key_prefix: str = "abc123",
    token: str | None = None,
    key_hash: str | None = None,
    deleted_at: datetime.datetime | None = None,
    last_used_at: datetime.datetime | None = None,
    created_at: datetime.datetime | None = None,
) -> dict[str, Any]:
    if token is not None:
        key_hash = _hash_token(token)
    if key_hash is None:
        key_hash = _hash_token(_make_token(key_prefix, "secret"))
    if created_at is None:
        created_at = _now() - datetime.timedelta(hours=1)
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "key_hash": key_hash,
        "deleted_at": deleted_at,
        "last_used_at": last_used_at,
        "created_at": created_at,
    }


class _FakeConn:
    def __init__(self, row: dict[str, Any] | None, *, update_error: Exception | None = None) -> None:
        self._row = row
        self._update_error = update_error
        self.updated: bool = False

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        return self._row

    async def execute(self, query: str, *args: Any) -> None:
        if self._update_error:
            raise self._update_error
        self.updated = True


class _FakePool:
    def __init__(self, row: dict[str, Any] | None = None, *, update_error: Exception | None = None) -> None:
        self._row = row
        self._update_error = update_error
        self.conn = _FakeConn(row, update_error=update_error)

    def acquire(self) -> "_FakeAcquire":
        return _FakeAcquire(self.conn)


class _FakeAcquire:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *args: Any) -> None:
        pass


def _make_request(pool: _FakePool | None) -> MagicMock:
    request = MagicMock()
    request.app.state.db_pool = pool
    return request


async def _call(
    token_header: str | None,
    pool: _FakePool | None,
    *,
    settings: Settings | None = None,
) -> None:
    if settings is None:
        settings = Settings()
    request = _make_request(pool)
    await require_scrape_token(
        request=request,
        authorization=token_header,
        settings=settings,
    )


def _valid_pool(prefix: str = "abc123", secret: str = "secret") -> _FakePool:
    token = _make_token(prefix, secret)
    return _FakePool(_make_row(key_prefix=prefix, token=token))


async def test_happy_path_valid_key_updates_last_used_at() -> None:
    prefix, secret = "abc123", "mysecret"
    token = _make_token(prefix, secret)
    pool = _FakePool(_make_row(key_prefix=prefix, token=token))
    await _call(f"Bearer {token}", pool)
    assert pool.conn.updated is True


async def test_missing_authorization_header_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await _call(None, _valid_pool())
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_token"


async def test_missing_bearer_keyword_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await _call("opk_abc123_secret", _valid_pool())
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_token"


async def test_wrong_scheme_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await _call("Token opk_abc123_secret", _valid_pool())
    assert exc.value.status_code == 401


async def test_bearer_no_token_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await _call("Bearer ", _valid_pool())
    assert exc.value.status_code == 401


async def test_token_without_opk_prefix_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await _call("Bearer notopk_abc_secret", _valid_pool())
    assert exc.value.status_code == 401


async def test_token_without_underscores_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await _call("Bearer plaintoken", _valid_pool())
    assert exc.value.status_code == 401


async def test_token_only_two_parts_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await _call("Bearer opk_onlytwoparts", _valid_pool())
    assert exc.value.status_code == 401


async def test_unknown_prefix_raises_401() -> None:
    pool = _FakePool(None)
    with pytest.raises(HTTPException) as exc:
        await _call("Bearer opk_unknownprefix_secret", pool)
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_token"


async def test_wrong_secret_raises_401() -> None:
    prefix = "abc123"
    token = _make_token(prefix, "correctsecret")
    pool = _FakePool(_make_row(key_prefix=prefix, token=token))
    with pytest.raises(HTTPException) as exc:
        await _call(f"Bearer opk_{prefix}_wrongsecret", pool)
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_token"


async def test_deleted_key_raises_401() -> None:
    prefix, secret = "abc123", "mysecret"
    token = _make_token(prefix, secret)
    row = _make_row(key_prefix=prefix, token=token, deleted_at=_now() - datetime.timedelta(days=1))
    pool = _FakePool(row)
    with pytest.raises(HTTPException) as exc:
        await _call(f"Bearer {token}", pool)
    assert exc.value.status_code == 401


async def test_never_used_old_key_raises_401() -> None:
    prefix, secret = "abc123", "mysecret"
    token = _make_token(prefix, secret)
    old_created = _now() - datetime.timedelta(hours=49)
    row = _make_row(key_prefix=prefix, token=token, last_used_at=None, created_at=old_created)
    pool = _FakePool(row)
    with pytest.raises(HTTPException) as exc:
        await _call(f"Bearer {token}", pool)
    assert exc.value.status_code == 401


async def test_never_used_fresh_key_succeeds() -> None:
    prefix, secret = "abc123", "mysecret"
    token = _make_token(prefix, secret)
    fresh_created = _now() - datetime.timedelta(hours=24)
    row = _make_row(key_prefix=prefix, token=token, last_used_at=None, created_at=fresh_created)
    pool = _FakePool(row)
    await _call(f"Bearer {token}", pool)
    assert pool.conn.updated is True


async def test_last_used_set_any_age_succeeds() -> None:
    prefix, secret = "abc123", "mysecret"
    token = _make_token(prefix, secret)
    old_created = _now() - datetime.timedelta(days=30)
    last_used = _now() - datetime.timedelta(days=29)
    row = _make_row(
        key_prefix=prefix,
        token=token,
        last_used_at=last_used,
        created_at=old_created,
    )
    pool = _FakePool(row)
    await _call(f"Bearer {token}", pool)
    assert pool.conn.updated is True


async def test_last_used_update_error_still_succeeds(caplog: pytest.LogCaptureFixture) -> None:
    prefix, secret = "abc123", "mysecret"
    token = _make_token(prefix, secret)
    pool = _FakePool(
        _make_row(key_prefix=prefix, token=token),
        update_error=RuntimeError("db write failed"),
    )
    with caplog.at_level(logging.WARNING, logger="src.auth.scrape_token"):
        await _call(f"Bearer {token}", pool)
    assert any("last_used_at" in r.message for r in caplog.records)


async def test_legacy_token_env_set_matches_header() -> None:
    settings = Settings(VIBECHECK_LEGACY_SCRAPE_TOKEN="legacy-static-token")
    request = _make_request(None)
    await require_scrape_token(
        request=request,
        authorization="Bearer legacy-static-token",
        settings=settings,
    )


async def test_legacy_token_env_set_wrong_value_falls_through_to_db() -> None:
    settings = Settings(VIBECHECK_LEGACY_SCRAPE_TOKEN="correct-legacy")
    prefix, secret = "abc123", "mysecret"
    token = _make_token(prefix, secret)
    pool = _FakePool(_make_row(key_prefix=prefix, token=token))
    request = _make_request(pool)
    await require_scrape_token(
        request=request,
        authorization=f"Bearer {token}",
        settings=settings,
    )
    assert pool.conn.updated is True


async def test_legacy_token_not_set_does_not_short_circuit() -> None:
    settings = Settings(VIBECHECK_LEGACY_SCRAPE_TOKEN=None)
    with pytest.raises(HTTPException) as exc:
        await _call("Bearer legacy-static-token", _FakePool(None), settings=settings)
    assert exc.value.status_code == 401
