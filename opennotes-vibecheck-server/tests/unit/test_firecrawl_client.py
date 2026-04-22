from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from src.firecrawl_client import (
    FIRECRAWL_API_BASE,
    FirecrawlClient,
    ScrapeMetadata,
    ScrapeResult,
)

SCRAPE_URL = f"{FIRECRAWL_API_BASE}/v2/scrape"
TARGET_URL = "https://example.com/article"


@pytest.fixture
def client() -> FirecrawlClient:
    return FirecrawlClient(api_key="test-key")


async def test_scrape_result_parses_realistic_firecrawl_response(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """scrape() returns a typed ScrapeResult with attribute access and alias mapping.

    Covers AC #1 (typed return with optional markdown/html/screenshot/links/metadata/
    warning) and AC #5 (ScrapeResult parses a realistic /v2/scrape envelope).
    Asserts on state, not interactions: we hit the HTTP mock once and inspect
    the returned object's attributes rather than dict keys.
    """
    envelope = {
        "success": True,
        "data": {
            "markdown": "# Hello World\n\nBody text.",
            "html": "<h1>Hello World</h1><p>Body text.</p>",
            "screenshot": "https://cdn.firecrawl.dev/shots/abc.png",
            "links": ["https://example.com/a", "https://example.com/b"],
            "metadata": {
                "title": "Hello World",
                "description": "An example page.",
                "language": "en",
                "sourceURL": "https://example.com/article",
                "statusCode": 200,
            },
        },
    }
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=envelope)

    result = await client.scrape(TARGET_URL, formats=["markdown", "html", "screenshot", "links"])

    assert isinstance(result, ScrapeResult)
    assert result.markdown == "# Hello World\n\nBody text."
    assert result.html == "<h1>Hello World</h1><p>Body text.</p>"
    assert result.screenshot == "https://cdn.firecrawl.dev/shots/abc.png"
    assert result.links == ["https://example.com/a", "https://example.com/b"]
    assert result.warning is None

    assert isinstance(result.metadata, ScrapeMetadata)
    assert result.metadata.title == "Hello World"
    assert result.metadata.description == "An example page."
    assert result.metadata.language == "en"
    # Alias mapping: Firecrawl sends camelCase; our model exposes snake_case.
    assert result.metadata.source_url == "https://example.com/article"
    assert result.metadata.status_code == 200
    assert result.metadata.error is None


async def test_scrape_result_handles_partial_formats(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """Formats not requested come back as None; screenshot-only scrape is valid."""
    envelope = {
        "success": True,
        "data": {
            "screenshot": "https://cdn.firecrawl.dev/shots/xyz.png",
            "metadata": {"sourceURL": "https://example.com/article", "statusCode": 200},
        },
    }
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=envelope)

    result = await client.scrape(TARGET_URL, formats=["screenshot"])

    assert result.markdown is None
    assert result.html is None
    assert result.links is None
    assert result.screenshot == "https://cdn.firecrawl.dev/shots/xyz.png"
    assert result.metadata is not None
    assert result.metadata.source_url == "https://example.com/article"


# --- Optional defaults + snake_case round-trip (P1.5 + P2.3) ---------------


def test_snake_case_input_accepted_by_scrape_result() -> None:
    """Python call sites can construct ScrapeResult with snake_case kwargs.

    With `populate_by_name=True` and explicit `default=None`, both the
    alias (camelCase, e.g. `rawHtml`) and the snake_case field name work
    as kwargs — and all optional fields default so callers can omit any.
    """
    result = ScrapeResult(raw_html="<p>x</p>")
    assert result.raw_html == "<p>x</p>"
    assert result.markdown is None
    assert result.html is None
    assert result.screenshot is None
    assert result.links is None
    assert result.metadata is None
    assert result.warning is None


def test_model_dump_emits_snake_case_by_default() -> None:
    """model_dump() must serialize using Python field names, not aliases.

    Tests and downstream Python code serialize ScrapeResult objects back
    to dicts; they expect snake_case keys. The camelCase aliases are a
    wire-format concern that only applies on the way *in* from Firecrawl.
    """
    result = ScrapeResult(raw_html="<p>y</p>")
    dumped = result.model_dump()
    assert "raw_html" in dumped
    assert "rawHtml" not in dumped
    assert dumped["raw_html"] == "<p>y</p>"


def test_raw_html_alias_roundtrips() -> None:
    """Firecrawl envelopes (`rawHtml` on the wire) populate `raw_html`."""
    result = ScrapeResult.model_validate({"rawHtml": "<p>wire</p>"})
    assert result.raw_html == "<p>wire</p>"


def test_source_url_alias_roundtrips() -> None:
    """ScrapeMetadata's `sourceURL` wire key maps to `source_url`."""
    meta = ScrapeMetadata.model_validate(
        {"sourceURL": "https://example.com/article", "statusCode": 201}
    )
    assert meta.source_url == "https://example.com/article"
    assert meta.status_code == 201


def test_scrape_result_empty_construction_is_valid() -> None:
    """Every ScrapeResult field is optional — `ScrapeResult()` must type-check and run."""
    result = ScrapeResult()
    assert result.raw_html is None
    assert result.metadata is None
