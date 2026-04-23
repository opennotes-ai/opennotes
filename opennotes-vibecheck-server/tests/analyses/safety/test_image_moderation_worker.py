from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.analyses.safety._schemas import ImageModerationMatch
from src.analyses.safety.image_moderation_worker import run_image_moderation
from src.analyses.safety.vision_client import SafeSearchResult, VisionTransientError
from src.config import Settings


def _make_settings(**overrides: Any) -> Settings:
    base = {
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

    url_to_result = {url: CLEAN_RESULT for url in images_per_utt[:30]}

    captured_urls: list[str] = []

    async def fake_annotate(urls, **kwargs):
        captured_urls.extend(urls)
        return {u: url_to_result.get(u) for u in urls}

    with caplog.at_level(logging.INFO, logger="src.analyses.safety.image_moderation_worker"):
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
    ):
        with pytest.raises(VisionTransientError, match="503"):
            await run_image_moderation(None, uuid4(), uuid4(), payload, settings)
