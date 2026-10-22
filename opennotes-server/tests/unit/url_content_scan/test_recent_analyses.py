from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.url_content_scan.recent_analyses import (
    _RECENT_SQL,
    _RECENT_UNFILTERED_SQL,
    _has_secret_query_param,
    _is_blocked_url,
    _passes_partial_threshold,
    list_recent,
    list_recent_unfiltered,
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


class _FakeUnfilteredAcquire:
    def __init__(self, rows: list[Mapping[str, object]], owner: _FakeUnfilteredPool) -> None:
        self._rows = rows
        self._owner = owner

    async def __aenter__(self) -> _FakeUnfilteredAcquire:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def fetch(self, query: str, limit: int) -> list[Mapping[str, object]]:
        self._owner.query = query
        self._owner.limit = limit
        return self._rows


class _FakeUnfilteredPool:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self._rows = rows
        self.query: str | None = None
        self.limit: int | None = None

    def acquire(self) -> _FakeUnfilteredAcquire:
        return _FakeUnfilteredAcquire(self._rows, self)


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
    deleted_at: datetime | None = None,
    x_og_thumbnail_url: str | None = None,
    headline_summary_text: str | None = None,
    weather_report_json: str | dict | None = None,
    safety_recommendation_json: str | dict | None = None,
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
        "deleted_at": deleted_at,
        "x_og_thumbnail_url": x_og_thumbnail_url,
        "headline_summary_text": headline_summary_text,
        "weather_report_json": weather_report_json,
        "safety_recommendation_json": safety_recommendation_json,
    }


def _unfiltered_row(
    *,
    normalized_url: str,
    source_url: str | None = None,
    status: str = "completed",
    storage_key: str | None = "shots/example.png",
    page_title: str = "Example Title",
    preview_description: str | None = "Preview text",
    finished_at: datetime | None = None,
    headline_summary_text: str | None = None,
    weather_report_json: str | dict | None = None,
    safety_recommendation_json: str | dict | None = None,
):
    return {
        "job_id": uuid4(),
        "normalized_url": normalized_url,
        "source_url": source_url or normalized_url,
        "status": status,
        "screenshot_storage_key": storage_key,
        "page_title": page_title,
        "preview_description": preview_description,
        "finished_at": finished_at or datetime.now(UTC),
        "headline_summary_text": headline_summary_text,
        "weather_report_json": weather_report_json,
        "safety_recommendation_json": safety_recommendation_json,
    }


def _partial_sections(done: int, total: int) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    for i in range(done):
        sections[f"slug-{i}"] = {"state": "done"}
    for i in range(done, total):
        sections[f"slug-{i}"] = {"state": "failed"}
    return sections


_WEATHER_JSON: dict = {
    "truth": {"label": "sourced", "logprob": None, "alternatives": []},
    "relevance": {"label": "insightful", "logprob": None, "alternatives": []},
    "sentiment": {"label": "positive", "logprob": None, "alternatives": []},
}

_SAFETY_JSON: dict = {
    "level": "caution",
    "rationale": "Some concerning content.",
    "top_signals": [],
    "unavailable_inputs": [],
    "divergences": [],
}


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
async def test_list_recent_strips_url_fragment_before_returning_source_url() -> None:
    pool = _FakePool(
        [
            _row(
                normalized_url="https://example.com/page",
                source_url="https://example.com/page#access_token=abc",
            )
        ]
    )

    result = await list_recent(pool, limit=5, signer=_StubSigner())

    assert len(result) == 1
    assert result[0].source_url == "https://example.com/page"


@pytest.mark.asyncio
async def test_list_recent_uses_sanitized_source_url_for_preview_fallback() -> None:
    pool = _FakePool(
        [
            _row(
                normalized_url="https://example.com/page",
                source_url="https://example.com/page#access_token=abc",
                page_title="",
                preview_description="https://example.com/page#access_token=abc",
            )
        ]
    )

    result = await list_recent(pool, limit=5, signer=_StubSigner())

    assert len(result) == 1
    assert result[0].preview_description == "https://example.com/page"
    assert "access_token" not in result[0].preview_description


@pytest.mark.asyncio
async def test_list_recent_overfetches_limit_times_eight() -> None:
    pool = _FakePool([_row(normalized_url="https://example.com/page")])

    await list_recent(pool, limit=3, signer=_StubSigner())

    assert pool.limit == 24
    assert pool.query == _RECENT_SQL


def test_recent_sql_prefers_interact_tier() -> None:
    assert "SELECT DISTINCT ON (normalized_url)" in _RECENT_SQL
    assert "CASE WHEN tier = 'interact' THEN 0 ELSE 1 END" in _RECENT_SQL


def test_recent_sql_excludes_soft_deleted_rows() -> None:
    assert "deleted_at IS NULL" in _RECENT_SQL


@pytest.mark.asyncio
async def test_list_recent_excludes_soft_deleted_job() -> None:
    pool = _FakePool(
        [
            _row(
                normalized_url="https://example.com/deleted",
                deleted_at=datetime.now(UTC) - timedelta(days=1),
            )
        ]
    )

    result = await list_recent(pool, limit=5, signer=_StubSigner())

    assert result == []


@pytest.mark.asyncio
async def test_list_recent_includes_non_soft_deleted_job() -> None:
    pool = _FakePool(
        [
            _row(
                normalized_url="https://example.com/active",
                deleted_at=None,
            )
        ]
    )

    result = await list_recent(pool, limit=5, signer=_StubSigner())

    assert len(result) == 1
    assert result[0].source_url == "https://example.com/active"


def test_recent_sql_selects_page_metadata_from_url_scan_state() -> None:
    assert "st.page_title" in _RECENT_SQL
    assert "st.page_kind" in _RECENT_SQL


def test_recent_sql_extracts_x_og_thumbnail_from_sidebar_payload() -> None:
    assert "x_og_thumbnail" in _RECENT_SQL


@pytest.mark.asyncio
async def test_list_recent_surfaces_x_og_thumbnail_url() -> None:
    pool = _FakePool(
        [
            _row(
                normalized_url="https://x.com/i/status/111",
                source_url="https://x.com/user/status/111",
                x_og_thumbnail_url="https://pbs.twimg.com/media/example.jpg",
            )
        ]
    )

    result = await list_recent(pool, limit=5, signer=_StubSigner())

    assert len(result) == 1
    assert result[0].og_thumbnail_url == "https://pbs.twimg.com/media/example.jpg"


@pytest.mark.asyncio
async def test_list_recent_og_thumbnail_url_is_none_for_non_x_rows() -> None:
    pool = _FakePool(
        [
            _row(
                normalized_url="https://example.com/article",
                x_og_thumbnail_url=None,
            )
        ]
    )

    result = await list_recent(pool, limit=5, signer=_StubSigner())

    assert len(result) == 1
    assert result[0].og_thumbnail_url is None


class TestHeadlinePreview:
    @pytest.mark.asyncio
    async def test_gallery_query_returns_headline_preview_from_headline_text(self) -> None:
        pool = _FakePool(
            [
                _row(
                    normalized_url="https://example.com/article",
                    headline_summary_text="This is the headline summary text.",
                )
            ]
        )

        result = await list_recent(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].headline_preview == "This is the headline summary text."

    @pytest.mark.asyncio
    async def test_gallery_query_headline_preview_is_none_when_missing(self) -> None:
        pool = _FakePool(
            [
                _row(
                    normalized_url="https://example.com/article",
                    headline_summary_text=None,
                )
            ]
        )

        result = await list_recent(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].headline_preview is None

    @pytest.mark.asyncio
    async def test_gallery_query_headline_preview_truncated_to_140_chars(self) -> None:
        long_text = "A" * 200
        pool = _FakePool(
            [
                _row(
                    normalized_url="https://example.com/article",
                    headline_summary_text=long_text,
                )
            ]
        )

        result = await list_recent(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].headline_preview is not None
        assert len(result[0].headline_preview) <= 140
        assert result[0].headline_preview.endswith("…")

    @pytest.mark.asyncio
    async def test_list_recent_unfiltered_returns_headline_preview(self) -> None:
        pool = _FakeUnfilteredPool(
            [
                _unfiltered_row(
                    normalized_url="https://example.com/article",
                    headline_summary_text="Unfiltered headline.",
                )
            ]
        )

        result = await list_recent_unfiltered(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].headline_preview == "Unfiltered headline."


class TestWeatherPreview:
    @pytest.mark.asyncio
    async def test_gallery_query_returns_weather_preview_extracted_from_weather_report(
        self,
    ) -> None:
        pool = _FakePool(
            [
                _row(
                    normalized_url="https://example.com/article",
                    weather_report_json=_WEATHER_JSON,
                )
            ]
        )

        result = await list_recent(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].weather_preview is not None
        assert "sourced" in result[0].weather_preview
        assert "insightful" in result[0].weather_preview
        assert "positive" in result[0].weather_preview

    @pytest.mark.asyncio
    async def test_gallery_query_weather_preview_is_none_when_no_weather(self) -> None:
        pool = _FakePool(
            [
                _row(
                    normalized_url="https://example.com/article",
                    weather_report_json=None,
                )
            ]
        )

        result = await list_recent(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].weather_preview is None

    @pytest.mark.asyncio
    async def test_gallery_query_weather_preview_none_on_invalid_json(self) -> None:
        pool = _FakePool(
            [
                _row(
                    normalized_url="https://example.com/article",
                    weather_report_json={"invalid": "shape"},
                )
            ]
        )

        result = await list_recent(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].weather_preview is None

    @pytest.mark.asyncio
    async def test_gallery_query_weather_preview_accepts_json_string(self) -> None:
        pool = _FakePool(
            [
                _row(
                    normalized_url="https://example.com/article",
                    weather_report_json=json.dumps(_WEATHER_JSON),
                )
            ]
        )

        result = await list_recent(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].weather_preview is not None

    @pytest.mark.asyncio
    async def test_list_recent_unfiltered_weather_preview_populated(self) -> None:
        pool = _FakeUnfilteredPool(
            [
                _unfiltered_row(
                    normalized_url="https://example.com/article",
                    weather_report_json=_WEATHER_JSON,
                )
            ]
        )

        result = await list_recent_unfiltered(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].weather_preview is not None
        assert "sourced" in result[0].weather_preview


class TestSafetyRow:
    @pytest.mark.asyncio
    async def test_gallery_query_returns_safety_row_summary(self) -> None:
        pool = _FakePool(
            [
                _row(
                    normalized_url="https://example.com/article",
                    safety_recommendation_json=_SAFETY_JSON,
                )
            ]
        )

        result = await list_recent(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].safety_row is not None
        assert result[0].safety_row.level == "caution"

    @pytest.mark.asyncio
    async def test_gallery_query_safety_row_is_none_when_no_recommendation(self) -> None:
        pool = _FakePool(
            [
                _row(
                    normalized_url="https://example.com/article",
                    safety_recommendation_json=None,
                )
            ]
        )

        result = await list_recent(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].safety_row is None

    @pytest.mark.asyncio
    async def test_gallery_query_safety_row_graceful_on_invalid_recommendation(self) -> None:
        pool = _FakePool(
            [
                _row(
                    normalized_url="https://example.com/article",
                    safety_recommendation_json={"invalid": "shape"},
                )
            ]
        )

        result = await list_recent(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].safety_row is None

    @pytest.mark.asyncio
    async def test_list_recent_unfiltered_safety_row_populated(self) -> None:
        pool = _FakeUnfilteredPool(
            [
                _unfiltered_row(
                    normalized_url="https://example.com/article",
                    safety_recommendation_json=_SAFETY_JSON,
                )
            ]
        )

        result = await list_recent_unfiltered(pool, limit=5, signer=_StubSigner())

        assert len(result) == 1
        assert result[0].safety_row is not None
        assert result[0].safety_row.level == "caution"


def test_recent_sql_selects_headline_summary_text() -> None:
    assert "headline" in _RECENT_SQL


def test_recent_sql_selects_weather_report_json() -> None:
    assert "weather_report" in _RECENT_SQL


def test_recent_sql_selects_safety_recommendation_json() -> None:
    assert "safety" in _RECENT_SQL


def test_recent_unfiltered_sql_selects_preview_fields() -> None:
    assert "headline" in _RECENT_UNFILTERED_SQL
    assert "weather_report" in _RECENT_UNFILTERED_SQL
    assert "safety" in _RECENT_UNFILTERED_SQL
