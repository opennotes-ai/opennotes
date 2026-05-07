from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.analyses.safety.image_moderation_worker import run_image_moderation
from src.analyses.safety.vision_client import SafeSearchResult, VisionTransientError
from src.config import Settings


def _make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "MAX_IMAGES_MODERATED": 30,
        "MAX_VIDEOS_MODERATED": 5,
    }
    base.update(overrides)
    return Settings(**base)


class _Utterance:
    def __init__(self, uid: str, images: list[str]):
        self.utterance_id = uid
        self.mentioned_images = images


class _Payload:
    def __init__(self, utterances: list[_Utterance]):
        self.utterances = utterances


CLEAN_RESULT = SafeSearchResult(
    adult=0.0,
    violence=0.0,
    racy=0.0,
    medical=0.0,
    spoof=0.0,
    flagged=False,
    max_likelihood=0.0,
)

FLAGGED_RESULT = SafeSearchResult(
    adult=1.0,
    violence=0.0,
    racy=0.0,
    medical=0.0,
    spoof=0.0,
    flagged=True,
    max_likelihood=1.0,
)


@pytest.mark.asyncio
async def test_empty_media_returns_no_matches_no_http():
    payload = _Payload([])
    settings = _make_settings()
    with patch(
        "src.analyses.safety.image_moderation_worker.annotate_images"
    ) as mock_annotate:
        result = await run_image_moderation(None, uuid4(), uuid4(), payload, settings)
    assert result == {"matches": []}
    mock_annotate.assert_not_called()


@pytest.mark.asyncio
async def test_flattens_per_utterance_images_in_order():
    payload = _Payload([
        _Utterance("utt-1", ["https://example.com/a.jpg", "https://example.com/b.jpg"]),
        _Utterance("utt-2", ["https://example.com/c.jpg"]),
    ])
    settings = _make_settings()
    url_to_result = {
        "https://example.com/a.jpg": CLEAN_RESULT,
        "https://example.com/b.jpg": CLEAN_RESULT,
        "https://example.com/c.jpg": CLEAN_RESULT,
    }
    with patch(
        "src.analyses.safety.image_moderation_worker.annotate_images",
        new=AsyncMock(return_value=url_to_result),
    ):
        result = await run_image_moderation(None, uuid4(), uuid4(), payload, settings)
    matches = result["matches"]
    assert len(matches) == 3
    assert matches[0]["utterance_id"] == "utt-1"
    assert matches[0]["image_url"] == "https://example.com/a.jpg"
    assert matches[1]["utterance_id"] == "utt-1"
    assert matches[1]["image_url"] == "https://example.com/b.jpg"
    assert matches[2]["utterance_id"] == "utt-2"
    assert matches[2]["image_url"] == "https://example.com/c.jpg"


@pytest.mark.asyncio
async def test_enforces_max_images_moderated_cap_logs_dropped(caplog):
    images_per_utt = [f"https://example.com/img{i}.jpg" for i in range(50)]
    payload = _Payload([_Utterance("utt-1", images_per_utt)])
    settings = _make_settings(MAX_IMAGES_MODERATED=30)

    url_to_result = dict.fromkeys(images_per_utt[:30], CLEAN_RESULT)

    captured_urls: list[str] = []

    async def fake_annotate(urls, **kwargs):
        captured_urls.extend(urls)
        return {u: url_to_result.get(u) for u in urls}

    with caplog.at_level(logging.INFO, logger="src.analyses.safety.image_moderation_worker"):  # noqa: SIM117
        with patch(
            "src.analyses.safety.image_moderation_worker.annotate_images",
            new=fake_annotate,
        ):
            result = await run_image_moderation(None, uuid4(), uuid4(), payload, settings)

    assert len(captured_urls) == 30
    assert len(result["matches"]) == 30
    assert any("dropped=20" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_skips_unfetchable_urls_result_none():
    payload = _Payload([
        _Utterance("utt-1", ["https://example.com/ok.jpg", "https://example.com/bad.jpg"]),
    ])
    settings = _make_settings()
    url_to_result = {
        "https://example.com/ok.jpg": CLEAN_RESULT,
        "https://example.com/bad.jpg": None,
    }
    with patch(
        "src.analyses.safety.image_moderation_worker.annotate_images",
        new=AsyncMock(return_value=url_to_result),
    ):
        result = await run_image_moderation(None, uuid4(), uuid4(), payload, settings)
    assert len(result["matches"]) == 1
    assert result["matches"][0]["image_url"] == "https://example.com/ok.jpg"


@pytest.mark.asyncio
async def test_emits_unflagged_matches_too():
    payload = _Payload([
        _Utterance("utt-1", ["https://example.com/clean.jpg"]),
    ])
    settings = _make_settings()
    url_to_result = {
        "https://example.com/clean.jpg": CLEAN_RESULT,
    }
    with patch(
        "src.analyses.safety.image_moderation_worker.annotate_images",
        new=AsyncMock(return_value=url_to_result),
    ):
        result = await run_image_moderation(None, uuid4(), uuid4(), payload, settings)
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert match["flagged"] is False
    assert match["max_likelihood"] == 0.0
    assert match["utterance_id"] == "utt-1"


@pytest.mark.asyncio
async def test_propagates_vision_transient_error():
    payload = _Payload([
        _Utterance("utt-1", ["https://example.com/img.jpg"]),
    ])
    settings = _make_settings()
    with patch(
        "src.analyses.safety.image_moderation_worker.annotate_images",
        new=AsyncMock(side_effect=VisionTransientError("vision 503")),
    ), pytest.raises(VisionTransientError, match="503"):
        await run_image_moderation(None, uuid4(), uuid4(), payload, settings)


# ---- TASK-1483.24.04: cache integration ----


class _StubPool:
    """In-memory stand-in for asyncpg.Pool exercising the cache module path."""

    def __init__(self, fetch_fn=None, upsert_fn=None):
        self._fetch_fn = fetch_fn
        self._upsert_fn = upsert_fn

    def _make_conn(self):
        outer = self

        class _Conn:
            async def fetch(self, _query, urls):
                return outer._fetch_fn(urls) if outer._fetch_fn else []

            async def executemany(self, _query, rows):
                if outer._upsert_fn:
                    outer._upsert_fn(rows)

        return _Conn()

    def acquire(self):
        outer = self

        class _CM:
            async def __aenter__(self):
                return outer._make_conn()

            async def __aexit__(self, *exc):
                return False

        return _CM()


@pytest.mark.asyncio
async def test_full_cache_hit_skips_annotate_images():
    payload = _Payload([
        _Utterance("utt-1", ["https://example.com/a.jpg", "https://example.com/b.jpg"]),
    ])
    settings = _make_settings()

    cached_payload = {
        "adult": 0.0, "violence": 0.0, "racy": 0.0, "medical": 0.0,
        "spoof": 0.0, "flagged": False, "max_likelihood": 0.0,
    }

    def fetch_fn(urls):
        return [{"image_url": u, "result_payload": cached_payload} for u in urls]

    pool = _StubPool(fetch_fn=fetch_fn)

    with patch(
        "src.analyses.safety.image_moderation_worker.annotate_images",
        new=AsyncMock(return_value={}),
    ) as mock_annotate:
        result = await run_image_moderation(pool, uuid4(), uuid4(), payload, settings)

    mock_annotate.assert_not_called()
    assert {m["image_url"] for m in result["matches"]} == {
        "https://example.com/a.jpg",
        "https://example.com/b.jpg",
    }


@pytest.mark.asyncio
async def test_partial_cache_hit_calls_annotate_only_for_missing():
    payload = _Payload([
        _Utterance("utt-1", [
            "https://example.com/cached.jpg",
            "https://example.com/fresh.jpg",
        ]),
    ])
    settings = _make_settings()

    cached_payload = {
        "adult": 0.0, "violence": 0.0, "racy": 0.0, "medical": 0.0,
        "spoof": 0.0, "flagged": False, "max_likelihood": 0.0,
    }

    def fetch_fn(urls):
        return [
            {"image_url": "https://example.com/cached.jpg", "result_payload": cached_payload}
        ]

    upserted_rows: list = []
    pool = _StubPool(fetch_fn=fetch_fn, upsert_fn=upserted_rows.extend)

    captured: list[list[str]] = []

    async def fake_annotate(urls, **kwargs):
        captured.append(list(urls))
        return {urls[0]: FLAGGED_RESULT}

    with patch(
        "src.analyses.safety.image_moderation_worker.annotate_images",
        new=fake_annotate,
    ):
        result = await run_image_moderation(pool, uuid4(), uuid4(), payload, settings)

    assert captured == [["https://example.com/fresh.jpg"]]
    assert {m["image_url"] for m in result["matches"]} == {
        "https://example.com/cached.jpg",
        "https://example.com/fresh.jpg",
    }
    # only fresh URL persisted to cache
    assert [r[0] for r in upserted_rows] == ["https://example.com/fresh.jpg"]


@pytest.mark.asyncio
async def test_cache_fetch_failure_falls_back_to_full_api(caplog):
    payload = _Payload([_Utterance("utt-1", ["https://example.com/a.jpg"])])
    settings = _make_settings()

    class _BrokenPool:
        def acquire(self):
            raise RuntimeError("db down")

    captured_calls: list[list[str]] = []

    async def fake_annotate(urls, **kwargs):
        captured_calls.append(list(urls))
        return {urls[0]: CLEAN_RESULT}

    with caplog.at_level(logging.ERROR, logger="src.analyses.safety.image_moderation_worker"):  # noqa: SIM117
        with patch(
            "src.analyses.safety.image_moderation_worker.annotate_images",
            new=fake_annotate,
        ):
            result = await run_image_moderation(
                _BrokenPool(), uuid4(), uuid4(), payload, settings
            )

    assert captured_calls == [["https://example.com/a.jpg"]]
    assert len(result["matches"]) == 1
    assert any("fetch_cached failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_all_images_unanalyzable_returns_empty_matches():
    urls = [
        "https://example.com/img1.jpg",
        "https://example.com/img2.jpg",
    ]
    payload = _Payload([_Utterance("utt-1", urls)])
    settings = _make_settings()

    with patch(
        "src.analyses.safety.image_moderation_worker.annotate_images",
        new=AsyncMock(return_value=dict.fromkeys(urls)),
    ):
        result = await run_image_moderation(None, uuid4(), uuid4(), payload, settings)

    assert result == {"matches": []}


@pytest.mark.asyncio
async def test_none_results_not_persisted_to_cache():
    payload = _Payload([
        _Utterance("utt-1", [
            "https://example.com/ok.jpg",
            "https://example.com/bad.jpg",
        ]),
    ])
    settings = _make_settings()

    upserted_rows: list = []
    pool = _StubPool(fetch_fn=lambda urls: [], upsert_fn=upserted_rows.extend)

    url_to_result = {
        "https://example.com/ok.jpg": CLEAN_RESULT,
        "https://example.com/bad.jpg": None,
    }
    with patch(
        "src.analyses.safety.image_moderation_worker.annotate_images",
        new=AsyncMock(return_value=url_to_result),
    ):
        await run_image_moderation(pool, uuid4(), uuid4(), payload, settings)

    assert [r[0] for r in upserted_rows] == ["https://example.com/ok.jpg"]
