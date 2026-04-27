from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from src.firecrawl_client import (
    FIRECRAWL_API_BASE,
    FirecrawlBlocked,
    FirecrawlClient,
    FirecrawlError,
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


async def test_scrape_request_body_wraps_formats_as_objects(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """TASK-1479: /v2/scrape rejects bare-string formats with invalid_union.

    The request body must wrap each format into `{"type": "<fmt>"}`, and
    the `screenshot@fullPage` shorthand must expand to the documented
    `{"type": "screenshot", "fullPage": true}` object. This test pins the
    exact wire shape so Firecrawl-side schema regressions break tests
    instead of production.
    """
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json={"success": True, "data": {}})

    await client.scrape(
        TARGET_URL,
        formats=["markdown", "html", "screenshot@fullPage"],
        only_main_content=True,
    )

    request = httpx_mock.get_request(url=SCRAPE_URL, method="POST")
    assert request is not None
    body = json.loads(request.content)
    assert body == {
        "url": TARGET_URL,
        "formats": [
            {"type": "markdown"},
            {"type": "html"},
            {"type": "screenshot", "fullPage": True},
        ],
        "onlyMainContent": True,
    }


# --- TASK-1488.02: FirecrawlBlocked + interact() + single-attempt mode ------


def test_firecrawl_blocked_is_subclass_of_firecrawl_error() -> None:
    """`FirecrawlBlocked` must extend `FirecrawlError` so existing
    `except FirecrawlError` blocks still catch refusals — but specific
    refusal-handling code can `except FirecrawlBlocked` first to branch.
    """
    assert issubclass(FirecrawlBlocked, FirecrawlError)


async def test_scrape_refusal_envelope_raises_firecrawl_blocked(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """An envelope `{success: false, error: "<refusal phrase>"}` must raise
    the typed `FirecrawlBlocked` so the orchestrator can fast-fail Tier 1
    instead of treating it as a transient error worth retrying.
    """
    envelope = {
        "success": False,
        "error": "this website is no longer supported",
    }
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=envelope)

    with pytest.raises(FirecrawlBlocked):
        await client.scrape(TARGET_URL, formats=["markdown"])


async def test_scrape_generic_failure_still_raises_firecrawl_error_not_blocked(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """Refusal markers must be conservative: a generic `success: false`
    envelope without a documented refusal phrase must raise the base
    `FirecrawlError`, NOT the more specific `FirecrawlBlocked`. False
    positives here would terminate legit content paths.
    """
    envelope = {
        "success": False,
        "error": "internal hiccup, please retry",
    }
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=envelope)

    with pytest.raises(FirecrawlError) as exc_info:
        await client.scrape(TARGET_URL, formats=["markdown"])
    assert not isinstance(exc_info.value, FirecrawlBlocked)


async def test_scrape_4xx_with_refusal_marker_raises_firecrawl_blocked(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """A 403/4xx body containing a documented refusal phrase must also
    surface as `FirecrawlBlocked` — Firecrawl sometimes signals refusals
    via HTTP status rather than `success: false`.
    """
    httpx_mock.add_response(
        url=SCRAPE_URL,
        method="POST",
        status_code=403,
        json={"error": "Firecrawl does not support this domain"},
    )

    with pytest.raises(FirecrawlBlocked):
        await client.scrape(TARGET_URL, formats=["markdown"])


async def test_interact_returns_scrape_result_on_success(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """`interact()` posts to /v2/scrape (with `actions`) and returns a typed
    `ScrapeResult` mirroring `scrape()`'s shape.

    TASK-1488.08: Firecrawl v2 has no /v2/interact endpoint — browser actions
    are run by /v2/scrape via the `actions` field. The public method name
    `interact()` is preserved so the orchestrator's Tier 2 wiring still calls
    `client.interact(...)`, but the request goes to /v2/scrape under the hood.
    """
    envelope = {
        "success": True,
        "data": {
            "markdown": "# After interaction\n\nRevealed content.",
            "html": "<h1>After interaction</h1><p>Revealed content.</p>",
            "screenshot": "https://cdn.firecrawl.dev/shots/interact.png",
            "metadata": {
                "title": "Interactive Page",
                "sourceURL": TARGET_URL,
                "statusCode": 200,
            },
        },
    }
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=envelope)

    result = await client.interact(
        TARGET_URL,
        actions=[{"type": "click", "selector": "#load-more"}],
    )

    assert isinstance(result, ScrapeResult)
    assert result.markdown == "# After interaction\n\nRevealed content."
    assert result.html == "<h1>After interaction</h1><p>Revealed content.</p>"
    assert result.screenshot == "https://cdn.firecrawl.dev/shots/interact.png"
    assert result.metadata is not None
    assert result.metadata.source_url == TARGET_URL


async def test_interact_routes_to_scrape_endpoint_with_actions_field(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """TASK-1488.08 AC #1: interact() must POST to /v2/scrape, not /v2/interact.

    Live calls against api.firecrawl.dev/v2/interact return 404 Cannot POST.
    Per Firecrawl v2 docs, browser actions are part of /v2/scrape via the
    `actions` field. Pin the URL so a regression to /v2/interact breaks tests
    instead of production.
    """
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json={"success": True, "data": {}})

    actions = [
        {"type": "click", "selector": "#consent-accept"},
        {"type": "wait", "milliseconds": 500},
    ]
    await client.interact(TARGET_URL, actions=actions)

    request = httpx_mock.get_request(url=SCRAPE_URL, method="POST")
    assert request is not None
    assert str(request.url) == SCRAPE_URL
    body = json.loads(request.content)
    assert body["url"] == TARGET_URL
    assert body["actions"] == actions
    assert body["formats"] == [
        {"type": "markdown"},
        {"type": "html"},
        {"type": "screenshot", "fullPage": True},
    ]


async def test_interact_refusal_envelope_raises_firecrawl_blocked(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """`interact()` shares refusal detection with `scrape()` — the same
    refusal markers that fast-fail Tier 1 must also fast-fail Tier 2.
    Now that interact routes through /v2/scrape, the mock URL is the same.
    """
    envelope = {
        "success": False,
        "error": "this website is blocked by Firecrawl policy",
    }
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=envelope)

    with pytest.raises(FirecrawlBlocked):
        await client.interact(TARGET_URL, actions=[{"type": "click", "selector": "#x"}])


async def test_max_attempts_one_disables_retry_on_503(
    httpx_mock: HTTPXMock,
) -> None:
    """Tier 1 fail-fast pattern: `FirecrawlClient(max_attempts=1)` must
    perform exactly ONE HTTP call before surfacing the error, even on
    normally-retryable 503s. Asserts on real call count via the mock,
    not on internals.
    """
    fast_client = FirecrawlClient(api_key="test-key", max_attempts=1)
    httpx_mock.add_response(
        url=SCRAPE_URL,
        method="POST",
        status_code=503,
        text="Service Unavailable",
    )

    # The retry wrapper re-raises a private retryable-status exception after
    # the budget is exhausted; this test cares about *call count*, not the
    # specific exception type. Matching on "503" still validates something
    # stable about the failure shape.
    with pytest.raises(Exception, match="503"):
        await fast_client.scrape(TARGET_URL, formats=["markdown"])

    requests = httpx_mock.get_requests(url=SCRAPE_URL, method="POST")
    assert len(requests) == 1


async def test_default_max_attempts_three_retries_on_503(
    httpx_mock: HTTPXMock,
) -> None:
    """Default `max_attempts=3` (Tier 2 callers) is preserved: a sustained
    503 must trigger the full retry budget. Pinning this protects Tier 2
    behavior from accidentally regressing when Tier 1 was added.
    """
    default_client = FirecrawlClient(api_key="test-key")
    for _ in range(3):
        httpx_mock.add_response(
            url=SCRAPE_URL,
            method="POST",
            status_code=503,
            text="Service Unavailable",
        )

    with pytest.raises(Exception, match="503"):
        await default_client.scrape(TARGET_URL, formats=["markdown"])

    requests = httpx_mock.get_requests(url=SCRAPE_URL, method="POST")
    assert len(requests) == 3


# --- TASK-1488.09: real-world refusal envelope ----------------------------


async def test_scrape_real_unsupported_site_envelope_raises_firecrawl_blocked(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """TASK-1488.09 AC #4: real Firecrawl refusal body for LinkedIn/Reddit.

    Live verification (TASK-1488.07) captured the real refusal envelope:
    `{"success":false,"error":"We apologize for the inconvenience but we do
    not support this site. If you are part of an enterprise..."}`. The
    previous marker list ("no longer supported", "firecrawl does not
    support", "this website is blocked") did NOT match this phrasing,
    causing legit refusals to be classified as TransientError and triggering
    infinite Cloud Tasks retries. This test pins the real wire phrase so a
    marker regression breaks the suite.
    """
    envelope = {
        "success": False,
        "error": (
            "We apologize for the inconvenience but we do not support this site. "
            "If you are part of an enterprise, please reach out to support@firecrawl.dev"
        ),
    }
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=envelope)

    with pytest.raises(FirecrawlBlocked):
        await client.scrape(TARGET_URL, formats=["markdown"])


async def test_refusal_marker_matches_case_insensitively(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """Case-insensitive match still works for the new marker. The orchestrator
    only differentiates `FirecrawlBlocked` from `FirecrawlError`; if Firecrawl
    ever returns the phrase in mixed case, we must still classify as a refusal.
    """
    envelope = {
        "success": False,
        "error": "WE DO NOT SUPPORT THIS SITE for legal reasons",
    }
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=envelope)

    with pytest.raises(FirecrawlBlocked):
        await client.scrape(TARGET_URL, formats=["markdown"])


# --- TASK-1488.10: language as list[str] ----------------------------------


def test_scrape_metadata_accepts_language_as_list() -> None:
    """TASK-1488.10 AC #1+#3: Cloudflare's blog returns
    `metadata.language=["en-us", "en"]` on real responses. The previous
    `str | None` annotation rejected this with a pydantic validation error,
    which the orchestrator caught as `FirecrawlError` -> `TransientError` ->
    infinite retry on a 200-OK page. Coerce list[str] to its first element
    so the model still validates.
    """
    meta = ScrapeMetadata.model_validate(
        {
            "title": "Page",
            "language": ["en-us", "en"],
            "sourceURL": "https://blog.cloudflare.com/page-rules-deprecation/",
            "statusCode": 200,
        }
    )
    assert meta.language == "en-us"


def test_scrape_metadata_accepts_language_as_string_unchanged() -> None:
    """Single-language string responses (the common case) keep working
    after the list-coercion validator is added. Regression guard for
    happy-path callers.
    """
    meta = ScrapeMetadata.model_validate({"language": "en"})
    assert meta.language == "en"


def test_scrape_metadata_accepts_empty_language_list() -> None:
    """Defensive: an empty list shouldn't blow up, just coerce to None."""
    meta = ScrapeMetadata.model_validate({"language": []})
    assert meta.language is None


async def test_scrape_full_envelope_with_language_list_succeeds(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    """End-to-end through `scrape()`: a real-shaped envelope with
    `metadata.language=["en-us", "en"]` must validate successfully and
    return a populated `ScrapeResult`. This is the path that was blowing
    up in production for blog.cloudflare.com.
    """
    envelope = {
        "success": True,
        "data": {
            "markdown": "# Page rules deprecation",
            "metadata": {
                "title": "Page rules deprecation",
                "language": ["en-us", "en"],
                "sourceURL": "https://blog.cloudflare.com/page-rules-deprecation/",
                "statusCode": 200,
            },
        },
    }
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=envelope)

    result = await client.scrape(TARGET_URL, formats=["markdown"])

    assert result.markdown == "# Page rules deprecation"
    assert result.metadata is not None
    assert result.metadata.language == "en-us"
