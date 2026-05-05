from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.url_content_scan.recent_analyses import (
    _RECENT_SQL,
    _has_secret_query_param,
    _is_blocked_url,
    _passes_partial_threshold,
    list_recent,
)


class _StubSigner:
    def __init__(self) -> None:
        self.keys: list[str | None] = []

    def sign_screenshot_key(self, storage_key: str | None) -> str | None:
        self.keys.append(storage_key)
        if not storage_key:
            return None
        return f"https://signed.example/{storage_key}"


class _FakeAcquire:
    def __init__(self, rows: list[Mapping[str, object]], owner: _FakePool) -> None:
        self._rows = rows
        self._owner = owner

    async def __aenter__(self) -> _FakeAcquire:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def fetch(self, query: str, limit: int) -> list[Mapping[str, object]]:
        self._owner.query = query
        self._owner.limit = limit
        return self._rows


class _FakePool:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self._rows = rows
        self.query: str | None = None
        self.limit: int | None = None

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self._rows, self)


def _row(
    *,
    normalized_url: str,
    source_url: str | None = None,
    status: str = "completed",
    sections: Mapping[str, Mapping[str, str]] | None = None,
    storage_key: str = "shots/example.png",
    page_title: str = "Example Title",
    preview_description: str = "Preview text",
    finished_at: datetime | None = None,
):
    return {
        "job_id": uuid4(),
        "normalized_url": normalized_url,
        "source_url": source_url or normalized_url,
        "status": status,
        "sections": sections or {f"slug-{i}": {"state": "done"} for i in range(10)},
        "screenshot_storage_key": storage_key,
        "page_title": page_title,
        "preview_description": preview_description,
        "finished_at": finished_at or datetime.now(UTC),
    }


def _partial_sections(done: int, total: int) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    for i in range(done):
        sections[f"slug-{i}"] = {"state": "done"}
    for i in range(done, total):
        sections[f"slug-{i}"] = {"state": "failed"}
    return sections


class TestSecretQueryFilter:
    @pytest.mark.parametrize(
        "param",
        [
            "token",
            "api_key",
            "secret",
            "access_token",
            "password",
            "auth",
            "sig",
            "signature",
            "key",
        ],
    )
    def test_blocks_secret_keys(self, param: str) -> None:
        assert _has_secret_query_param(f"{param}=abc") is True

    def test_allows_innocuous_query(self) -> None:
        assert _has_secret_query_param("page=2&sort=desc") is False


class TestBlockedUrlFilter:
    def test_blocks_secret_query(self) -> None:
        assert _is_blocked_url("https://example.com/page?token=abc") is True

    def test_blocks_explicit_non_safe_port(self) -> None:
        assert _is_blocked_url("https://example.com:9000/page") is True

    def test_blocks_userinfo(self) -> None:
        assert _is_blocked_url("https://user:pass@example.com/page") is True

    def test_blocks_validate_public_http_url_rejections(self) -> None:
        assert _is_blocked_url("http://127.0.0.1/private") is True

    def test_allows_public_https_url(self) -> None:
        assert _is_blocked_url("https://example.com/page") is False


class TestPartialThreshold:
    def test_done_passes_unconditionally(self) -> None:
        assert _passes_partial_threshold({}, "completed") is True

    def test_partial_under_threshold_fails(self) -> None:
        assert _passes_partial_threshold(_partial_sections(done=8, total=10), "partial") is False

    def test_partial_at_threshold_passes(self) -> None:
        assert _passes_partial_threshold(_partial_sections(done=9, total=10), "partial") is True


@pytest.mark.asyncio
async def test_list_recent_includes_done_job_with_signed_screenshot_url() -> None:
    finished_at = datetime.now(UTC)
    pool = _FakePool(
        [
            _row(
                normalized_url="https://example.com/done",
                finished_at=finished_at,
                storage_key="shots/done.png",
            )
        ]
    )
    signer = _StubSigner()

    result = await list_recent(pool, limit=5, signer=signer)

    assert len(result) == 1
    assert result[0].source_url == "https://example.com/done"
    assert result[0].screenshot_url == "https://signed.example/shots/done.png"
    assert result[0].completed_at == finished_at
    assert signer.keys == ["shots/done.png"]


@pytest.mark.asyncio
async def test_list_recent_excludes_under_threshold_partial() -> None:
    pool = _FakePool(
        [
            _row(
                normalized_url="https://example.com/partial",
                status="partial",
                sections=_partial_sections(done=8, total=10),
            )
        ]
    )

    result = await list_recent(pool, limit=5, signer=_StubSigner())

    assert result == []


@pytest.mark.asyncio
async def test_list_recent_keeps_older_qualifying_duplicate_when_newer_row_is_privacy_blocked() -> (
    None
):
    older = _row(
        normalized_url="https://example.com/dup",
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
        preview_description="older preview",
    )
    newer_blocked = _row(
        normalized_url="https://example.com/dup",
        source_url="https://example.com/dup?token=secret",
        finished_at=datetime.now(UTC),
        preview_description="newer blocked preview",
    )
    pool = _FakePool([newer_blocked, older])

    result = await list_recent(pool, limit=5, signer=_StubSigner())

    assert len(result) == 1
    assert result[0].job_id == older["job_id"]
    assert result[0].preview_description == "older preview"
    assert "?token=" not in result[0].source_url


@pytest.mark.asyncio
async def test_list_recent_blocks_secret_query_param_url() -> None:
    pool = _FakePool(
        [
            _row(
                normalized_url="https://example.com/page",
                source_url="https://example.com/page?signature=abc",
            )
        ]
    )

    result = await list_recent(pool, limit=5, signer=_StubSigner())

    assert result == []


@pytest.mark.asyncio
async def test_list_recent_blocks_explicit_non_80_port_url() -> None:
    pool = _FakePool(
        [
            _row(
                normalized_url="https://example.com/page",
                source_url="https://example.com:8080/page",
            )
        ]
    )

    result = await list_recent(pool, limit=5, signer=_StubSigner())

    assert result == []


@pytest.mark.asyncio
async def test_list_recent_overfetches_limit_times_eight() -> None:
    pool = _FakePool([_row(normalized_url="https://example.com/page")])

    await list_recent(pool, limit=3, signer=_StubSigner())

    assert pool.limit == 24
    assert pool.query == _RECENT_SQL


def test_recent_sql_prefers_interact_tier() -> None:
    assert "SELECT DISTINCT ON (normalized_url)" in _RECENT_SQL
    assert "CASE WHEN tier = 'interact' THEN 0 ELSE 1 END" in _RECENT_SQL
