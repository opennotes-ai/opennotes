from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from src.services.firecrawl_client import (
    FIRECRAWL_API_BASE,
    FirecrawlBlocked,
    FirecrawlClient,
    FirecrawlError,
    ScrapeMetadata,
    ScrapeResult,
)

SCRAPE_URL = f"{FIRECRAWL_API_BASE}/v2/scrape"
TARGET_URL = "https://example.com/article"
pytestmark = pytest.mark.unit


@dataclass
class _ResponseSpec:
    status_code: int = 200
    json_data: Any | None = None
    text: str | None = None

    def build(self, method: str, url: str, body: dict[str, Any] | None) -> httpx.Response:
        request = httpx.Request(method, url, json=body)
        if self.json_data is not None:
            return httpx.Response(self.status_code, json=self.json_data, request=request)
        return httpx.Response(self.status_code, text=self.text or "", request=request)


@pytest.fixture
def firecrawl_http_stub():
    requests: list[dict[str, Any]] = []
    response_specs: list[_ResponseSpec] = []

    class _StubAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self) -> _StubAsyncClient:
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str] | None = None,
            json: dict[str, Any] | None = None,
        ) -> httpx.Response:
            requests.append({"method": "POST", "url": url, "headers": headers, "json": json})
            if not response_specs:
                raise AssertionError("No stubbed response left for POST request")
            return response_specs.pop(0).build("POST", url, json)

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str] | None = None,
        ) -> httpx.Response:
            requests.append({"method": "GET", "url": url, "headers": headers, "json": None})
            if not response_specs:
                raise AssertionError("No stubbed response left for GET request")
            return response_specs.pop(0).build("GET", url, None)

    def add_response(
        *,
        url: str,
        method: str = "POST",
        status_code: int = 200,
        json_data: Any | None = None,
        text: str | None = None,
    ) -> None:
        assert url == SCRAPE_URL
        assert method == "POST"
        response_specs.append(
            _ResponseSpec(status_code=status_code, json_data=json_data, text=text)
        )

    def get_requests(*, url: str, method: str = "POST") -> list[dict[str, Any]]:
        return [
            request for request in requests if request["url"] == url and request["method"] == method
        ]

    with patch("src.services.firecrawl_client.httpx.AsyncClient", _StubAsyncClient):
        yield {
            "add_response": add_response,
            "get_requests": get_requests,
        }


@pytest.fixture
def client() -> FirecrawlClient:
    return FirecrawlClient(api_key="test-key")


async def test_scrape_result_parses_realistic_firecrawl_response(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
    envelope = {
        "success": True,
        "data": {
            "markdown": "# Hello World\n\nBody text.",
            "html": "<h1>Hello World</h1><p>Body text.</p>",
            "screenshot": "https://cdn.firecrawl.dev/shots/abc.png",
            "links": ["https://example.com/a", "https://example.com/b"],
            "actions": {
                "javascriptReturns": [{"type": "object", "value": "coral_status:copied;comments=2"}]
            },
            "metadata": {
                "title": "Hello World",
                "description": "An example page.",
                "language": "en",
                "sourceURL": "https://example.com/article",
                "statusCode": 200,
            },
        },
    }
    firecrawl_http_stub["add_response"](url=SCRAPE_URL, method="POST", json_data=envelope)

    result = await client.scrape(TARGET_URL, formats=["markdown", "html", "screenshot", "links"])

    assert isinstance(result, ScrapeResult)
    assert result.markdown == "# Hello World\n\nBody text."
    assert result.html == "<h1>Hello World</h1><p>Body text.</p>"
    assert result.screenshot == "https://cdn.firecrawl.dev/shots/abc.png"
    assert result.links == ["https://example.com/a", "https://example.com/b"]
    assert result.actions == {
        "javascriptReturns": [{"type": "object", "value": "coral_status:copied;comments=2"}]
    }
    assert result.warning is None
    assert isinstance(result.metadata, ScrapeMetadata)
    assert result.metadata.source_url == "https://example.com/article"
    assert result.metadata.status_code == 200


async def test_scrape_request_body_wraps_formats_as_objects(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
    firecrawl_http_stub["add_response"](
        url=SCRAPE_URL, method="POST", json_data={"success": True, "data": {}}
    )

    await client.scrape(
        TARGET_URL,
        formats=["markdown", "html", "screenshot@fullPage"],
        only_main_content=True,
    )

    request = firecrawl_http_stub["get_requests"](url=SCRAPE_URL, method="POST")[0]
    body = request["json"]
    assert body == {
        "url": TARGET_URL,
        "formats": [
            {"type": "markdown"},
            {"type": "html"},
            {"type": "screenshot", "fullPage": True},
        ],
        "onlyMainContent": True,
    }


async def test_scrape_refusal_envelope_raises_firecrawl_blocked(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
    firecrawl_http_stub["add_response"](
        url=SCRAPE_URL,
        method="POST",
        json_data={"success": False, "error": "this website is no longer supported"},
    )

    with pytest.raises(FirecrawlBlocked):
        await client.scrape(TARGET_URL, formats=["markdown"])


async def test_scrape_exact_site_refusal_marker_raises_firecrawl_blocked(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
    firecrawl_http_stub["add_response"](
        url=SCRAPE_URL,
        method="POST",
        json_data={"success": False, "error": "We do not support this site right now."},
    )

    with pytest.raises(FirecrawlBlocked, match="refused"):
        await client.scrape(TARGET_URL, formats=["markdown"])


async def test_scrape_generic_failure_still_raises_firecrawl_error_not_blocked(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
    firecrawl_http_stub["add_response"](
        url=SCRAPE_URL,
        method="POST",
        json_data={"success": False, "error": "internal hiccup, please retry"},
    )

    with pytest.raises(FirecrawlError) as exc_info:
        await client.scrape(TARGET_URL, formats=["markdown"])
    assert not isinstance(exc_info.value, FirecrawlBlocked)


async def test_scrape_4xx_with_refusal_marker_raises_firecrawl_blocked(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
    firecrawl_http_stub["add_response"](
        url=SCRAPE_URL,
        method="POST",
        status_code=403,
        json_data={"error": "Firecrawl does not support this domain"},
    )

    with pytest.raises(FirecrawlBlocked):
        await client.scrape(TARGET_URL, formats=["markdown"])


async def test_interact_returns_scrape_result_on_success(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
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
    firecrawl_http_stub["add_response"](url=SCRAPE_URL, method="POST", json_data=envelope)

    result = await client.interact(
        TARGET_URL,
        actions=[{"type": "click", "selector": "#load-more"}],
    )

    assert isinstance(result, ScrapeResult)
    assert result.markdown == "# After interaction\n\nRevealed content."
    assert result.metadata is not None
    assert result.metadata.source_url == TARGET_URL


async def test_interact_refusal_envelope_raises_firecrawl_blocked(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
    firecrawl_http_stub["add_response"](
        url=SCRAPE_URL,
        method="POST",
        json_data={"success": False, "error": "We do not support this site."},
    )

    with pytest.raises(FirecrawlBlocked, match="refused"):
        await client.interact(TARGET_URL, actions=[{"type": "click", "selector": "#paywall"}])


async def test_interact_routes_to_scrape_endpoint_with_actions_field(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
    firecrawl_http_stub["add_response"](
        url=SCRAPE_URL, method="POST", json_data={"success": True, "data": {}}
    )

    actions = [
        {"type": "click", "selector": "#consent-accept"},
        {"type": "wait", "milliseconds": 500},
    ]
    await client.interact(TARGET_URL, actions=actions)

    request = firecrawl_http_stub["get_requests"](url=SCRAPE_URL, method="POST")[0]
    body = request["json"]
    assert body["url"] == TARGET_URL
    assert body["actions"] == actions
    assert body["formats"] == [
        {"type": "markdown"},
        {"type": "html"},
        {"type": "screenshot", "fullPage": True},
    ]


async def test_interact_sends_only_main_content_false(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
    firecrawl_http_stub["add_response"](
        url=SCRAPE_URL, method="POST", json_data={"success": True, "data": {}}
    )

    await client.interact(
        TARGET_URL,
        actions=[{"type": "wait", "milliseconds": 100}],
        only_main_content=False,
    )

    request = firecrawl_http_stub["get_requests"](url=SCRAPE_URL, method="POST")[0]
    body = request["json"]
    assert body["onlyMainContent"] is False


async def test_max_attempts_one_disables_retry_on_503(
    firecrawl_http_stub: dict[str, Any],
) -> None:
    fast_client = FirecrawlClient(api_key="test-key", max_attempts=1)
    firecrawl_http_stub["add_response"](
        url=SCRAPE_URL,
        method="POST",
        status_code=503,
        text="Service Unavailable",
    )

    with pytest.raises(Exception, match="503"):
        await fast_client.scrape(TARGET_URL, formats=["markdown"])

    requests = firecrawl_http_stub["get_requests"](url=SCRAPE_URL, method="POST")
    assert len(requests) == 1


async def test_default_max_attempts_three_retries_on_503(
    firecrawl_http_stub: dict[str, Any],
) -> None:
    default_client = FirecrawlClient(api_key="test-key")
    for _ in range(3):
        firecrawl_http_stub["add_response"](
            url=SCRAPE_URL,
            method="POST",
            status_code=503,
            text="Service Unavailable",
        )

    with pytest.raises(Exception, match="503"):
        await default_client.scrape(TARGET_URL, formats=["markdown"])

    requests = firecrawl_http_stub["get_requests"](url=SCRAPE_URL, method="POST")
    assert len(requests) == 3


async def test_scrape_result_coerces_language_list_from_realistic_envelope(
    client: FirecrawlClient,
    firecrawl_http_stub: dict[str, Any],
) -> None:
    envelope = {
        "success": True,
        "data": {
            "markdown": "# Page\n\nBody text.",
            "metadata": {
                "title": "Page",
                "description": "A realistic scrape payload.",
                "language": ["en-us", "en"],
                "sourceURL": "https://blog.cloudflare.com/page-rules-deprecation/",
                "statusCode": 200,
            },
        },
    }
    firecrawl_http_stub["add_response"](url=SCRAPE_URL, method="POST", json_data=envelope)

    result = await client.scrape(TARGET_URL, formats=["markdown"])

    assert result.metadata is not None
    assert result.metadata.language == "en-us"
