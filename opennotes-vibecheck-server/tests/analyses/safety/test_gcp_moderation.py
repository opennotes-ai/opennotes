"""Tests for GCP Natural Language moderateText client.

TDD: tests written before implementation. Each test covers one AC
from TASK-1474.08.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from unittest.mock import patch

import httpx
import pytest

from src.analyses.safety._schemas import HarmfulContentMatch
from src.analyses.safety.gcp_moderation import (
    GcpModerationTransientError,
    moderate_texts_gcp,
)
from src.utterances.schema import Utterance


def make_utterance(
    utterance_id: str | None = "utt_1",
    text: str = "some text",
) -> Utterance:
    return Utterance(
        utterance_id=utterance_id,
        kind="post",
        text=text,
        author="alice",
    )


def make_moderation_response(categories: Sequence[Mapping[str, object]]) -> httpx.Response:
    """Build a mock GCP moderateText response."""
    import json

    body = json.dumps({"moderationCategories": categories})
    return httpx.Response(200, content=body.encode(), headers={"content-type": "application/json"})


class TestEmptyInput:
    async def test_empty_list_returns_empty_no_api_calls(self):
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return make_moderation_response([])

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value="tok"):
                result = await moderate_texts_gcp([], httpx_client=client)

        assert result == []
        assert call_count == 0


class TestEmptyText:
    async def test_empty_text_returns_none_slot_no_api_call(self):
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return make_moderation_response([])

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value="tok"):
                result = await moderate_texts_gcp(
                    [make_utterance(text="")],
                    httpx_client=client,
                )

        assert result == []
        assert call_count == 0


class TestBelowThreshold:
    async def test_all_below_threshold_returns_none(self):
        categories = [
            {"name": "Toxic", "confidence": 0.3},
            {"name": "Insult", "confidence": 0.2},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return make_moderation_response(categories)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value="tok"):
                result = await moderate_texts_gcp(
                    [make_utterance()],
                    httpx_client=client,
                    threshold=0.5,
                )

        assert result == []


class TestAboveThreshold:
    async def test_above_threshold_returns_match_with_source_gcp(self):
        categories = [{"name": "Toxic", "confidence": 0.9}]

        def handler(request: httpx.Request) -> httpx.Response:
            return make_moderation_response(categories)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value="tok"):
                result = await moderate_texts_gcp(
                    [make_utterance(utterance_id="utt_42")],
                    httpx_client=client,
                    threshold=0.5,
                )

        assert len(result) == 1
        match = result[0]
        assert match is not None
        assert isinstance(match, HarmfulContentMatch)
        assert match.source == "gcp"
        assert match.flagged_categories == ["Toxic"]
        assert match.max_score == pytest.approx(0.9)

    async def test_long_utterance_emits_chunk_match_and_aggregate(self):
        long_text = "toxic sentence in a long post. " * 500
        requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            payload = json.loads(request.content.decode())
            content = payload["document"]["content"]
            requests.append(content)
            confidence = 0.9 if len(requests) == 1 else 0.1
            return make_moderation_response([{"name": "Toxic", "confidence": confidence}])

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value="tok"):
                result = await moderate_texts_gcp(
                    [make_utterance(utterance_id="utt_long", text=long_text)],
                    httpx_client=client,
                    threshold=0.5,
                )

        assert len(requests) > 1
        assert len(result) == 2
        chunk_match = result[0]
        aggregate = result[1]
        assert chunk_match.chunk_idx == 0
        assert chunk_match.chunk_count is not None
        assert chunk_match.chunk_count > 1
        assert chunk_match.utterance_text != long_text
        assert aggregate.chunk_idx is None
        assert aggregate.chunk_count == chunk_match.chunk_count
        assert aggregate.utterance_text == long_text


class TestMultipleCategories:
    async def test_multiple_categories_flagged_correctly(self):
        categories = [
            {"name": "Toxic", "confidence": 0.1},
            {"name": "Insult", "confidence": 0.6},
            {"name": "Profanity", "confidence": 0.8},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return make_moderation_response(categories)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value="tok"):
                result = await moderate_texts_gcp(
                    [make_utterance()],
                    httpx_client=client,
                    threshold=0.5,
                )

        match = result[0]
        assert match is not None
        assert set(match.flagged_categories) == {"Insult", "Profanity"}
        assert match.categories["Toxic"] is False
        assert match.categories["Insult"] is True
        assert match.categories["Profanity"] is True
        assert match.max_score == pytest.approx(0.8)


class TestTransientErrors:
    async def test_429_raises_transient_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value="tok"):
                with pytest.raises(GcpModerationTransientError):
                    await moderate_texts_gcp(
                        [make_utterance()],
                        httpx_client=client,
                    )

    async def test_500_raises_transient_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value="tok"):
                with pytest.raises(GcpModerationTransientError):
                    await moderate_texts_gcp(
                        [make_utterance()],
                        httpx_client=client,
                    )

    async def test_missing_adc_token_raises_transient_error(self):
        transport = httpx.MockTransport(lambda _: httpx.Response(200))
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value=None):
                with pytest.raises(GcpModerationTransientError):
                    await moderate_texts_gcp(
                        [make_utterance()],
                        httpx_client=client,
                    )


class TestConcurrency:
    async def test_concurrency_bounded_by_semaphore(self):
        """Verify that no more than 8 requests are in-flight simultaneously."""
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def async_handler(request: httpx.Request) -> httpx.Response:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.01)
            async with lock:
                current_concurrent -= 1
            return make_moderation_response([{"name": "Toxic", "confidence": 0.1}])

        class TrackingTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                return await async_handler(request)

        utterances = [make_utterance(utterance_id=f"utt_{i}", text=f"text {i}") for i in range(20)]
        async with httpx.AsyncClient(transport=TrackingTransport()) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value="tok"):
                await moderate_texts_gcp(utterances, httpx_client=client)

        assert max_concurrent <= 8


class TestUtteranceId:
    async def test_passes_utterance_id_to_match(self):
        categories = [{"name": "Toxic", "confidence": 0.9}]

        def handler(request: httpx.Request) -> httpx.Response:
            return make_moderation_response(categories)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("src.analyses.safety.gcp_moderation.get_access_token", return_value="tok"):
                result = await moderate_texts_gcp(
                    [make_utterance(utterance_id="special-id-999")],
                    httpx_client=client,
                )

        match = result[0]
        assert match is not None
        assert match.utterance_id == "special-id-999"
