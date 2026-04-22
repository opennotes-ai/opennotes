from __future__ import annotations

import logging
from datetime import date

import httpx
import pytest
from pytest_httpx import HTTPXMock

from src.analyses.claims import known_misinfo as km
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.claims.known_misinfo import (
    FACT_CHECK_API_URL,
    check_known_misinformation,
)


@pytest.fixture(autouse=True)
def _stub_adc_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass google.auth.default() — tests don't need real ADC."""
    km._reset_cached_credentials_for_tests()
    monkeypatch.setattr(km, "_get_access_token", lambda: "stub-bearer-token")


@pytest.fixture
async def httpx_client():
    async with httpx.AsyncClient() as client:
        yield client


async def test_matched_response_maps_to_fact_check_rows(
    httpx_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=f"{FACT_CHECK_API_URL}?query=vaccines+cause+autism&languageCode=en&pageSize=5",
        method="GET",
        json={
            "claims": [
                {
                    "text": "Vaccines cause autism",
                    "claimant": "Random Blog",
                    "claimDate": "2021-01-01T00:00:00Z",
                    "claimReview": [
                        {
                            "publisher": {"name": "Snopes", "site": "snopes.com"},
                            "url": "https://snopes.com/fact-check/vaccines-autism",
                            "title": "Do vaccines cause autism?",
                            "reviewDate": "2021-02-01T00:00:00Z",
                            "textualRating": "False",
                            "languageCode": "en",
                        },
                        {
                            "publisher": {"name": "PolitiFact", "site": "politifact.com"},
                            "url": "https://politifact.com/factchecks/vaccines-autism",
                            "title": "Vaccines and autism claim debunked",
                            "reviewDate": "2021-03-15T00:00:00Z",
                            "textualRating": "Pants on Fire",
                            "languageCode": "en",
                        },
                    ],
                }
            ]
        },
    )

    matches = await check_known_misinformation(
        "vaccines cause autism",
        httpx_client=httpx_client,
    )

    assert len(matches) == 2
    assert all(isinstance(m, FactCheckMatch) for m in matches)

    first = matches[0]
    assert first.claim_text == "vaccines cause autism"
    assert first.publisher == "Snopes"
    assert first.review_title == "Do vaccines cause autism?"
    assert first.review_url == "https://snopes.com/fact-check/vaccines-autism"
    assert first.textual_rating == "False"
    assert first.review_date == date(2021, 2, 1)

    second = matches[1]
    assert second.publisher == "PolitiFact"
    assert second.textual_rating == "Pants on Fire"
    assert second.review_date == date(2021, 3, 15)


async def test_empty_response_returns_empty_list(
    httpx_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=f"{FACT_CHECK_API_URL}?query=no+matches+here&languageCode=en&pageSize=5",
        method="GET",
        json={},
    )

    matches = await check_known_misinformation(
        "no matches here",
        httpx_client=httpx_client,
    )

    assert matches == []


async def test_rate_limit_429_returns_empty_list_and_warns(
    httpx_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    httpx_mock.add_response(
        url=f"{FACT_CHECK_API_URL}?query=rate+limited+claim&languageCode=en&pageSize=5",
        method="GET",
        status_code=429,
        json={"error": {"code": 429, "message": "Rate limit exceeded"}},
    )

    with caplog.at_level(logging.WARNING, logger="src.analyses.claims.known_misinfo"):
        matches = await check_known_misinformation(
            "rate limited claim",
            httpx_client=httpx_client,
        )

    assert matches == []
    assert any(
        "429" in record.getMessage() or "rate" in record.getMessage().lower()
        for record in caplog.records
        if record.levelno == logging.WARNING
    )


async def test_limits_results_to_top_five_claim_reviews(
    httpx_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
) -> None:
    reviews = [
        {
            "publisher": {"name": f"Pub{i}", "site": f"pub{i}.com"},
            "url": f"https://pub{i}.com/factcheck",
            "title": f"Review {i}",
            "reviewDate": "2024-01-01T00:00:00Z",
            "textualRating": "False",
        }
        for i in range(8)
    ]
    httpx_mock.add_response(
        url=f"{FACT_CHECK_API_URL}?query=many+reviews&languageCode=en&pageSize=5",
        method="GET",
        json={"claims": [{"text": "many reviews", "claimReview": reviews}]},
    )

    matches = await check_known_misinformation(
        "many reviews",
        httpx_client=httpx_client,
    )

    assert len(matches) == 5


async def test_server_error_returns_empty_list_and_warns(
    httpx_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    httpx_mock.add_response(
        url=f"{FACT_CHECK_API_URL}?query=server+down&languageCode=en&pageSize=5",
        method="GET",
        status_code=500,
        json={"error": {"code": 500, "message": "Internal Server Error"}},
    )

    with caplog.at_level(logging.WARNING, logger="src.analyses.claims.known_misinfo"):
        matches = await check_known_misinformation(
            "server down",
            httpx_client=httpx_client,
        )

    assert matches == []


async def test_missing_optional_fields_are_tolerated(
    httpx_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=f"{FACT_CHECK_API_URL}?query=partial+data&languageCode=en&pageSize=5",
        method="GET",
        json={
            "claims": [
                {
                    "text": "partial data",
                    "claimReview": [
                        {
                            "publisher": {"name": "Some Publisher"},
                            "url": "https://example.com/fc",
                            "title": "A review",
                            "textualRating": "Mostly False",
                        }
                    ],
                }
            ]
        },
    )

    matches = await check_known_misinformation(
        "partial data",
        httpx_client=httpx_client,
    )

    assert len(matches) == 1
    assert matches[0].review_date is None
    assert matches[0].publisher == "Some Publisher"
