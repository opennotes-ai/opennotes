from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest

from src.services.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.utils.url_security import InvalidURL

_FRAME_PATH = Path(__file__).resolve().parents[3] / "src" / "url_content_scan" / "frame.py"
_PACKAGE_NAME = "src.url_content_scan"

if _PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(_PACKAGE_NAME)
    package.__path__ = [str(_FRAME_PATH.parent)]  # type: ignore[attr-defined]
    sys.modules[_PACKAGE_NAME] = package

_SPEC = importlib.util.spec_from_file_location("src.url_content_scan.frame", _FRAME_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["src.url_content_scan.frame"] = _MODULE
_SPEC.loader.exec_module(_MODULE)

archive_preview = _MODULE.archive_preview
frame_compat = _MODULE.frame_compat
lookup_screenshot = _MODULE.lookup_screenshot


@dataclass
class _FakeResponse:
    status_code: int
    headers: dict[str, str]


class _FakeHttpClient:
    def __init__(self, responses: dict[tuple[str, str], _FakeResponse]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    async def request(self, method: str, url: str) -> _FakeResponse:
        key = (method, url)
        self.calls.append(key)
        response = self._responses.get(key)
        if response is None:
            raise AssertionError(f"unexpected request: {key}")
        return response


@dataclass
class _CachedScrape:
    html: str | None = None
    markdown: str | None = None
    metadata: ScrapeMetadata | None = None
    storage_key: str | None = None


class _FakeScrapeCache:
    def __init__(self, cached_by_tier: dict[str, _CachedScrape | None] | None = None) -> None:
        self._cached_by_tier = cached_by_tier or {}
        self.get_calls: list[tuple[str, str]] = []
        self.put_calls: list[tuple[str, str]] = []
        self.evict_calls: list[tuple[str, str]] = []
        self.stored: _CachedScrape | None = None

    async def get(self, url: str, *, tier: str = "scrape") -> _CachedScrape | None:
        self.get_calls.append((url, tier))
        return self._cached_by_tier.get(tier)

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None = None,
        *,
        tier: str = "scrape",
    ) -> _CachedScrape:
        assert screenshot_bytes is None
        self.put_calls.append((url, tier))
        self.stored = _CachedScrape(
            html=scrape.html,
            markdown=scrape.markdown,
            metadata=scrape.metadata,
            storage_key="shots/generated.png",
        )
        return self.stored

    async def evict(self, url: str, *, tier: str = "scrape") -> None:
        self.evict_calls.append((url, tier))


class _FakeScraper:
    def __init__(self, result: ScrapeResult) -> None:
        self._result = result
        self.calls: list[tuple[str, tuple[str, ...], bool]] = []

    async def scrape(
        self,
        url: str,
        formats: list[str],
        *,
        only_main_content: bool = False,
    ) -> ScrapeResult:
        self.calls.append((url, tuple(formats), only_main_content))
        return self._result


class _FakeScreenshotStore:
    def __init__(self, signed_url: str = "https://signed.example/shots/example.png") -> None:
        self.signed_url = signed_url
        self.calls: list[tuple[str, timedelta]] = []

    async def sign_url(self, storage_key: str, *, ttl: timedelta) -> str:
        self.calls.append((storage_key, ttl))
        return self.signed_url


def _scrape(
    *,
    html: str | None = "<main><p>Body text</p></main>",
    markdown: str | None = "# Example\n\nBody text",
    source_url: str = "https://example.com/article",
) -> _CachedScrape:
    return _CachedScrape(
        html=html,
        markdown=markdown,
        metadata=ScrapeMetadata(title="Example", source_url=source_url, status_code=200),
        storage_key="shots/example.png",
    )


def _scrape_result(
    *,
    html: str | None = "<main><p>Body text</p></main>",
    markdown: str | None = "# Example\n\nBody text",
    source_url: str = "https://example.com/article",
) -> ScrapeResult:
    return ScrapeResult(
        html=html,
        markdown=markdown,
        metadata=ScrapeMetadata(title="Example", source_url=source_url, status_code=200),
    )


@pytest.mark.asyncio
async def test_frame_compat_blocks_xfo_and_reports_missing_archive() -> None:
    client = _FakeHttpClient(
        {
            ("HEAD", "https://example.com/article"): _FakeResponse(
                status_code=200,
                headers={"x-frame-options": "DENY"},
            )
        }
    )

    result = await frame_compat(
        "https://example.com/article",
        client=client,
        scrape_cache=_FakeScrapeCache(),
    )

    assert result.can_iframe is False
    assert result.blocking_header == "x-frame-options: DENY"
    assert result.csp_frame_ancestors is None
    assert result.has_archive is False
    assert client.calls == [("HEAD", "https://example.com/article")]


@pytest.mark.asyncio
async def test_frame_compat_falls_back_to_get_and_uses_interact_archive() -> None:
    client = _FakeHttpClient(
        {
            ("HEAD", "https://example.com/article"): _FakeResponse(
                status_code=405,
                headers={},
            ),
            ("GET", "https://example.com/article"): _FakeResponse(
                status_code=200,
                headers={
                    "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
                },
            ),
        }
    )
    cache = _FakeScrapeCache(cached_by_tier={"interact": _scrape()})

    result = await frame_compat("https://example.com/article", client=client, scrape_cache=cache)

    assert result.can_iframe is False
    assert result.blocking_header == "content-security-policy: frame-ancestors none"
    assert result.csp_frame_ancestors == "frame-ancestors 'none'"
    assert result.has_archive is True
    assert client.calls == [
        ("HEAD", "https://example.com/article"),
        ("GET", "https://example.com/article"),
    ]
    assert cache.get_calls == [
        ("https://example.com/article", "browser_html"),
        ("https://example.com/article", "interact"),
    ]


@pytest.mark.asyncio
async def test_archive_preview_prefers_cached_interact_html() -> None:
    cache = _FakeScrapeCache(
        cached_by_tier={
            "interact": _scrape(html="<main><!--x--><script>bad()</script><p>keep</p></main>")
        }
    )

    result = await archive_preview("https://example.com/article", scrape_cache=cache)

    assert result == "<main><p>keep</p></main>"
    assert cache.get_calls == [
        ("https://example.com/article", "browser_html"),
        ("https://example.com/article", "interact"),
    ]
    assert cache.put_calls == []


@pytest.mark.asyncio
async def test_archive_preview_generates_and_stores_when_requested() -> None:
    cache = _FakeScrapeCache()
    scraper = _FakeScraper(
        _scrape_result(
            html="<main><!--x--><script>bad()</script><p>keep</p></main>",
            source_url="https://example.com/final",
        )
    )

    result = await archive_preview(
        "https://example.com/article",
        scrape_cache=cache,
        scraper=scraper,
        generate=True,
    )

    assert result == "<main><p>keep</p></main>"
    assert scraper.calls == [
        ("https://example.com/article", ("html",), True),
    ]
    assert cache.put_calls == [("https://example.com/article", "scrape")]


@pytest.mark.asyncio
async def test_archive_preview_evicts_cached_tier_when_final_url_is_not_public() -> None:
    cache = _FakeScrapeCache(
        cached_by_tier={"scrape": _scrape(source_url="http://127.0.0.1/private")}
    )

    with pytest.raises(InvalidURL) as exc_info:
        await archive_preview("https://example.com/article", scrape_cache=cache)

    assert exc_info.value.reason == "private_ip"
    assert cache.evict_calls == [("https://example.com/article", "scrape")]


@pytest.mark.asyncio
async def test_lookup_screenshot_returns_signed_url_with_fifteen_minute_ttl() -> None:
    cache = _FakeScrapeCache(cached_by_tier={"interact": _scrape()})
    screenshot_store = _FakeScreenshotStore()

    result = await lookup_screenshot(
        "https://example.com/article",
        scrape_cache=cache,
        screenshot_store=screenshot_store,
    )

    assert result == {"screenshot_url": "https://signed.example/shots/example.png"}
    assert cache.get_calls == [
        ("https://example.com/article", "browser_html"),
        ("https://example.com/article", "interact"),
    ]
    assert screenshot_store.calls == [("shots/example.png", timedelta(minutes=15))]


@pytest.mark.asyncio
async def test_lookup_screenshot_returns_none_when_storage_key_missing() -> None:
    cache = _FakeScrapeCache(
        cached_by_tier={"scrape": _CachedScrape(html="<main>cached</main>", storage_key=None)}
    )

    result = await lookup_screenshot(
        "https://example.com/article",
        scrape_cache=cache,
        screenshot_store=_FakeScreenshotStore(),
    )

    assert result is None
    assert cache.get_calls == [
        ("https://example.com/article", "browser_html"),
        ("https://example.com/article", "interact"),
        ("https://example.com/article", "scrape"),
    ]
