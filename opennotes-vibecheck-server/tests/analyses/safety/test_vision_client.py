from __future__ import annotations

import base64
import json
from unittest.mock import patch

import httpx
import pytest

from src.analyses.safety.vision_client import (
    ANNOTATE_URL,
    FLAG_THRESHOLD,
    SafeSearchResult,
    VisionTransientError,
    annotate_images,
)

CLEAN_ANNOTATION = {
    "adult": "VERY_UNLIKELY",
    "violence": "VERY_UNLIKELY",
    "racy": "VERY_UNLIKELY",
    "medical": "VERY_UNLIKELY",
    "spoof": "VERY_UNLIKELY",
}

ADULT_ANNOTATION = {
    "adult": "VERY_LIKELY",
    "violence": "VERY_UNLIKELY",
    "racy": "VERY_UNLIKELY",
    "medical": "VERY_UNLIKELY",
    "spoof": "VERY_UNLIKELY",
}

FAKE_TOKEN = "fake-token-xyz"


def _vision_response(annotations: list[dict]) -> dict:
    return {"responses": [{"safeSearchAnnotation": a} for a in annotations]}


def _vision_error_response() -> dict:
    return {"responses": [{"error": {"code": 400, "message": "URL fetch failed"}}]}


def _make_transport(routes: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, str(request.url))
        for (method, url_prefix), resp in routes.items():
            if request.method == method and str(request.url).startswith(url_prefix):
                return resp
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture()
def mock_token():
    with patch("src.analyses.safety.vision_client.get_access_token", return_value=FAKE_TOKEN):
        yield


@pytest.fixture()
def no_token():
    with patch("src.analyses.safety.vision_client.get_access_token", return_value=None):
        yield


@pytest.mark.asyncio
async def test_empty_list_returns_empty(mock_token):
    async with httpx.AsyncClient() as client:
        result = await annotate_images([], httpx_client=client)
    assert result == {}


@pytest.mark.asyncio
async def test_batch_of_three_clean_images(mock_token):
    urls = [
        "https://example.com/img1.jpg",
        "https://example.com/img2.jpg",
        "https://example.com/img3.jpg",
    ]
    vision_resp = _vision_response([CLEAN_ANNOTATION] * 3)

    transport = _make_transport(
        {("POST", ANNOTATE_URL): httpx.Response(200, json=vision_resp)}
    )
    async with httpx.AsyncClient(transport=transport) as client:
        results = await annotate_images(urls, httpx_client=client)

    assert len(results) == 3
    for url in urls:
        r = results[url]
        assert isinstance(r, SafeSearchResult)
        assert r.flagged is False
        assert r.adult == 0.0
        assert r.max_likelihood == 0.0


@pytest.mark.asyncio
async def test_very_likely_adult_flagged(mock_token):
    url = "https://example.com/adult.jpg"
    vision_resp = _vision_response([ADULT_ANNOTATION])

    transport = _make_transport(
        {("POST", ANNOTATE_URL): httpx.Response(200, json=vision_resp)}
    )
    async with httpx.AsyncClient(transport=transport) as client:
        results = await annotate_images([url], httpx_client=client)

    r = results[url]
    assert isinstance(r, SafeSearchResult)
    assert r.adult == 1.0
    assert r.flagged is True
    assert r.max_likelihood == 1.0


@pytest.mark.asyncio
async def test_batch_larger_than_16_splits_into_multiple_requests(mock_token):
    urls = [f"https://example.com/img{i}.jpg" for i in range(20)]

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if str(request.url) == ANNOTATE_URL and request.method == "POST":
            call_count += 1
            body = json.loads(request.content)
            batch_size = len(body["requests"])
            resp = _vision_response([CLEAN_ANNOTATION] * batch_size)
            return httpx.Response(200, json=resp)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await annotate_images(urls, httpx_client=client)

    assert call_count == 2
    assert len(results) == 20
    for url in urls:
        assert results[url] is not None
        assert results[url].flagged is False


@pytest.mark.asyncio
async def test_url_fetch_failure_triggers_inline_fallback(mock_token):
    url = "https://cdn.example.com/protected.jpg"
    fake_image_bytes = b"FAKE_IMAGE_DATA"
    b64_encoded = base64.b64encode(fake_image_bytes).decode("ascii")

    annotate_call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal annotate_call_count
        if str(request.url) == ANNOTATE_URL and request.method == "POST":
            annotate_call_count += 1
            body = json.loads(request.content)
            req = body["requests"][0]
            if "source" in req["image"]:
                return httpx.Response(200, json=_vision_error_response())
            else:
                return httpx.Response(200, json=_vision_response([CLEAN_ANNOTATION]))
        if str(request.url) == url and request.method == "GET":
            return httpx.Response(
                200,
                content=fake_image_bytes,
                headers={"content-type": "image/jpeg"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await annotate_images([url], httpx_client=client)

    assert annotate_call_count == 2
    r = results[url]
    assert isinstance(r, SafeSearchResult)
    assert r.flagged is False


@pytest.mark.asyncio
async def test_inline_fallback_404_returns_none(mock_token):
    url = "https://cdn.example.com/gone.jpg"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == ANNOTATE_URL and request.method == "POST":
            return httpx.Response(200, json=_vision_error_response())
        if str(request.url) == url and request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await annotate_images([url], httpx_client=client)

    assert results[url] is None


@pytest.mark.asyncio
async def test_inline_fallback_exceeds_size_cap_returns_none(mock_token):
    url = "https://cdn.example.com/huge.jpg"
    big_bytes = b"X" * 100

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == ANNOTATE_URL and request.method == "POST":
            return httpx.Response(200, json=_vision_error_response())
        if str(request.url) == url and request.method == "GET":
            return httpx.Response(
                200,
                content=big_bytes,
                headers={"content-type": "image/jpeg"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await annotate_images([url], httpx_client=client, max_bytes_inline=50)

    assert results[url] is None


@pytest.mark.asyncio
async def test_data_url_returns_none_no_api_call(mock_token):
    data_url = "data:image/png;base64,abc123"

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"responses": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await annotate_images([data_url], httpx_client=client)

    assert call_count == 0
    assert results[data_url] is None


@pytest.mark.asyncio
async def test_ftp_url_returns_none_no_api_call(mock_token):
    ftp_url = "ftp://files.example.com/image.jpg"

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"responses": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await annotate_images([ftp_url], httpx_client=client)

    assert call_count == 0
    assert results[ftp_url] is None


@pytest.mark.asyncio
async def test_429_raises_transient_error(mock_token):
    url = "https://example.com/img.jpg"

    transport = _make_transport(
        {("POST", ANNOTATE_URL): httpx.Response(429)}
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(VisionTransientError, match="429"):
            await annotate_images([url], httpx_client=client)


@pytest.mark.asyncio
async def test_5xx_raises_transient_error(mock_token):
    url = "https://example.com/img.jpg"

    transport = _make_transport(
        {("POST", ANNOTATE_URL): httpx.Response(503)}
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(VisionTransientError, match="503"):
            await annotate_images([url], httpx_client=client)


@pytest.mark.asyncio
async def test_missing_token_raises_transient_error(no_token):
    url = "https://example.com/img.jpg"

    async with httpx.AsyncClient() as client:
        with pytest.raises(VisionTransientError, match="ADC token unavailable"):
            await annotate_images([url], httpx_client=client)
