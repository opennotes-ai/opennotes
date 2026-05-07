import asyncio
import time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

from src.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _client_state(client: TestClient) -> Any:
    return cast(Any, client.app).state


class _FakeAcquire:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    async def __aenter__(self) -> Any:
        return self.conn

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _FakePool:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self.conn)


def _fake_request_with_pool(pool: Any) -> Any:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db_pool=pool)))


class TestFrameCompat:
    def test_xfo_deny_returns_cannot_iframe(self, client: TestClient, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="HEAD",
            url="https://blocked.example.com/",
            headers={"x-frame-options": "DENY"},
        )
        resp = client.get("/api/frame-compat", params={"url": "https://blocked.example.com/"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_iframe"] is False
        assert body["blocking_header"] == "x-frame-options: DENY"
        assert body["has_archive"] is False

    def test_xfo_sameorigin_returns_cannot_iframe(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="HEAD",
            url="https://same.example.com/",
            headers={"x-frame-options": "SAMEORIGIN"},
        )
        resp = client.get("/api/frame-compat", params={"url": "https://same.example.com/"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_iframe"] is False
        assert "sameorigin" in body["blocking_header"].lower()

    def test_no_blocking_headers_allows_iframe(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="HEAD",
            url="https://open.example.com/",
            headers={"content-type": "text/html"},
        )
        resp = client.get("/api/frame-compat", params={"url": "https://open.example.com/"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_iframe"] is True
        assert body["blocking_header"] is None
        assert body["has_archive"] is False

    def test_has_archive_is_true_when_cached_html_exists(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        from src.cache.scrape_cache import CachedScrape

        calls: list[str] = []

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                assert url == "https://archived.example.com/"
                calls.append(tier)
                if tier == "browser_html":
                    return None
                if tier == "interact":
                    return None
                return CachedScrape(html="<main>Archived</main>")

        httpx_mock.add_response(
            method="HEAD",
            url="https://archived.example.com/",
            headers={"x-frame-options": "DENY"},
        )
        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/frame-compat", params={"url": "https://archived.example.com/"}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_iframe"] is False
        assert body["has_archive"] is True
        assert calls == ["interact", "scrape"]

    def test_has_archive_is_true_for_browser_html_job(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        job_id = "11111111-1111-1111-1111-111111111111"

        class StubConn:
            async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
                assert "vibecheck_scrapes" in query
                assert args == (
                    UUID(job_id),
                    "https://extension-cache.example.com/",
                )
                return {
                    "url": "https://extension-cache.example.com/",
                    "final_url": "https://extension-cache.example.com/",
                    "page_title": "Extension submitted",
                    "markdown": "Extension submitted article body",
                    "html": "<main>Extension submitted article body</main>",
                    "screenshot_storage_key": None,
                }

        class StubCache:
            async def get(self, url: str, *, tier: str = "scrape") -> None:
                raise AssertionError("browser_html lookup must be job-scoped")

        httpx_mock.add_response(
            method="HEAD",
            url="https://extension-cache.example.com/",
            headers={"x-frame-options": "DENY"},
        )
        _client_state(client).db_pool = _FakePool(StubConn())
        try:
            with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
                resp = client.get(
                    "/api/frame-compat",
                    params={
                        "url": "https://extension-cache.example.com/",
                        "job_id": job_id,
                    },
                )
        finally:
            del _client_state(client).db_pool
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_iframe"] is False
        assert body["has_archive"] is True

    def test_has_archive_uses_interact_tier_first(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        from src.cache.scrape_cache import CachedScrape

        calls: list[str] = []

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                assert url == "https://interact-cache.example.com/"
                calls.append(tier)
                if tier == "browser_html":
                    return None
                if tier == "interact":
                    return CachedScrape(html="<main>Interact archived</main>")
                return None

        httpx_mock.add_response(
            method="HEAD",
            url="https://interact-cache.example.com/",
            headers={"x-frame-options": "DENY"},
        )
        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/frame-compat", params={"url": "https://interact-cache.example.com/"}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_iframe"] is False
        assert body["has_archive"] is True
        assert calls == ["interact"]

    def test_has_archive_is_false_for_non_ok_tier_one_html(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        from src.cache.scrape_cache import CachedScrape

        calls: list[str] = []

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                assert url == "https://interstitial-archive.example.com/"
                calls.append(tier)
                if tier == "browser_html":
                    return None
                if tier == "interact":
                    return None
                return CachedScrape(html="<main>Just a moment</main>")

        httpx_mock.add_response(
            method="HEAD",
            url="https://interstitial-archive.example.com/",
            headers={"x-frame-options": "DENY"},
        )
        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/frame-compat",
                params={"url": "https://interstitial-archive.example.com/"},
            )
        assert resp.status_code == 200
        assert resp.json()["has_archive"] is False
        assert calls == ["interact", "scrape"]

    def test_has_archive_is_false_when_no_tier_has_html(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        calls: list[str] = []

        class StubCache:
            async def get(self, url: str, *, tier: str = "scrape") -> None:
                assert url == "https://archive-miss.example.com/"
                calls.append(tier)

        httpx_mock.add_response(
            method="HEAD",
            url="https://archive-miss.example.com/",
            headers={"x-frame-options": "DENY"},
        )
        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/frame-compat", params={"url": "https://archive-miss.example.com/"}
            )
        assert resp.status_code == 200
        assert resp.json()["has_archive"] is False
        assert calls == ["interact", "scrape"]

    def test_csp_frame_ancestors_none_blocks(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="HEAD",
            url="https://csp.example.com/",
            headers={"content-security-policy": "frame-ancestors 'none'"},
        )
        resp = client.get("/api/frame-compat", params={"url": "https://csp.example.com/"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_iframe"] is False
        assert "frame-ancestors" in body["blocking_header"]
        assert body["csp_frame_ancestors"] == "frame-ancestors 'none'"

    def test_csp_frame_ancestors_self_blocks(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="HEAD",
            url="https://self.example.com/",
            headers={"content-security-policy": "default-src 'self'; frame-ancestors 'self'"},
        )
        resp = client.get("/api/frame-compat", params={"url": "https://self.example.com/"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_iframe"] is False

    def test_csp_frame_ancestors_wildcard_allows(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="HEAD",
            url="https://wildcard.example.com/",
            headers={"content-security-policy": "frame-ancestors *"},
        )
        resp = client.get("/api/frame-compat", params={"url": "https://wildcard.example.com/"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_iframe"] is True
        assert body["csp_frame_ancestors"] == "frame-ancestors *"

    def test_head_405_falls_back_to_get(self, client: TestClient, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="HEAD",
            url="https://no-head.example.com/",
            status_code=405,
        )
        httpx_mock.add_response(
            method="GET",
            url="https://no-head.example.com/",
            headers={"x-frame-options": "DENY"},
        )
        resp = client.get("/api/frame-compat", params={"url": "https://no-head.example.com/"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_iframe"] is False

    def test_missing_url_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/frame-compat")
        assert resp.status_code == 422

    def test_invalid_url_returns_400(self, client: TestClient) -> None:
        resp = client.get("/api/frame-compat", params={"url": "not-a-url"})
        assert resp.status_code == 400

    @pytest.mark.parametrize(
        ("trigger_url", "monkeypatch_dns", "expected_detail"),
        [
            # scheme_not_allowed
            ("javascript:alert(1)", None, "URL must be an http(s) URL"),
            # missing_host — bare scheme with no netloc.
            ("http:///path", None, "URL must include a host"),
            # invalid_host — IDNA-illegal host (consecutive dots / label > 63).
            (
                "https://" + "a" * 64 + ".example.com/",
                None,
                "URL host is invalid",
            ),
            # host_blocked — localhost is on the static allowlist deny.
            ("http://localhost/", None, "URL host is not allowed"),
            # private_ip — RFC1918 IP literal.
            ("http://10.0.0.1/admin", None, "URL points to a private network address"),
            # resolved_private_ip — public-looking host that resolves to RFC1918.
            (
                "http://evil.example.com/",
                "private",
                "URL points to a private network address",
            ),
            # unresolvable_host — getaddrinfo raises socket.gaierror.
            (
                "http://this-host-must-not-exist.example.invalid/",
                "unresolvable",
                "URL host could not be resolved",
            ),
        ],
    )
    def test_invalid_url_reason_maps_to_human_readable_detail(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        trigger_url: str,
        monkeypatch_dns: str | None,
        expected_detail: str,
    ) -> None:
        """Each `InvalidURL.reason` slug must map to its pinned human-readable copy.

        The mapping in `routes/frame.py:_REASON_TO_HUMAN_DETAIL` exists so
        frontend clients pinning the older copy don't break across the
        SSRF refactor. TASK-1473.50: parametrize over every reason the
        SSRF guard can raise so any new reason added without a mapping
        falls through to the catch-all `"URL is not allowed"` and this
        test fails loudly instead of silently drifting.
        """
        import socket

        if monkeypatch_dns == "private":
            def _resolve_to_private(
                *_args: object, **_kwargs: object
            ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
                return [
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0))
                ]

            monkeypatch.setattr(socket, "getaddrinfo", _resolve_to_private)
        elif monkeypatch_dns == "unresolvable":
            def _gaierror(
                *_args: object, **_kwargs: object
            ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
                raise socket.gaierror("no such host")

            monkeypatch.setattr(socket, "getaddrinfo", _gaierror)

        resp = client.get("/api/frame-compat", params={"url": trigger_url})
        assert resp.status_code == 400, resp.text
        assert resp.json() == {"detail": expected_detail}


class TestScreenshot:
    @pytest.mark.asyncio
    async def test_stored_screenshot_lookup_uses_browser_html_job_first(self) -> None:
        from src.routes.frame import _lookup_stored_screenshot_key

        calls: list[tuple[object, ...]] = []

        class StubConn:
            async def fetchval(self, query: str, *args: object) -> str | None:
                assert "screenshot_storage_key IS NOT NULL" in query
                calls.append(args)
                return "screenshots/browser-html.png"

        key = await _lookup_stored_screenshot_key(
            _fake_request_with_pool(_FakePool(StubConn())),
            url="https://example.com/article",
            job_id=UUID("11111111-1111-1111-1111-111111111111"),
        )

        assert key == "screenshots/browser-html.png"
        assert calls == [
            (
                UUID("11111111-1111-1111-1111-111111111111"),
                "https://example.com/article",
            )
        ]

    @pytest.mark.asyncio
    async def test_stored_screenshot_lookup_falls_back_to_firecrawl_tiers(self) -> None:
        from src.routes.frame import _lookup_stored_screenshot_key

        calls: list[tuple[object, ...]] = []

        class StubConn:
            async def fetchval(self, query: str, *args: object) -> str | None:
                assert "evicted_at IS NULL" in query
                assert "expires_at > now()" in query
                calls.append(args)
                if args[-1] == "interact":
                    return "screenshots/interact.png"
                return None

        key = await _lookup_stored_screenshot_key(
            _fake_request_with_pool(_FakePool(StubConn())),
            url="https://example.com/article",
            job_id=None,
        )

        assert key == "screenshots/interact.png"
        assert calls == [("https://example.com/article", "interact")]

    @pytest.mark.asyncio
    async def test_stored_screenshot_lookup_returns_none_when_no_tier_matches(self) -> None:
        from src.routes.frame import _lookup_stored_screenshot_key

        calls: list[tuple[object, ...]] = []

        class StubConn:
            async def fetchval(self, query: str, *args: object) -> None:
                calls.append(args)

        key = await _lookup_stored_screenshot_key(
            _fake_request_with_pool(_FakePool(StubConn())),
            url="https://example.com/article",
            job_id=None,
        )

        assert key is None
        assert calls == [
            ("https://example.com/article", "interact"),
            ("https://example.com/article", "scrape"),
        ]

    @pytest.mark.asyncio
    async def test_stored_screenshot_lookup_returns_none_when_database_unavailable(
        self,
    ) -> None:
        from src.routes.frame import _lookup_stored_screenshot_key

        key = await _lookup_stored_screenshot_key(
            _fake_request_with_pool(None),
            url="https://example.com/article",
            job_id=UUID("11111111-1111-1111-1111-111111111111"),
        )

        assert key is None

    def test_returns_screenshot_url(self, client: TestClient) -> None:
        from src.firecrawl_client import ScrapeResult

        stub_result = ScrapeResult(screenshot="https://cdn.firecrawl.dev/shots/abc.png")

        class StubClient:
            async def scrape(self, url: str, formats: list[str]) -> ScrapeResult:
                return stub_result

        with patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()):
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )
        assert resp.status_code == 200
        assert resp.json() == {"screenshot_url": "https://cdn.firecrawl.dev/shots/abc.png"}

    def test_falls_back_to_metadata_screenshot(self, client: TestClient) -> None:
        from src.firecrawl_client import ScrapeMetadata, ScrapeResult

        # ScrapeMetadata has extra='allow' — a `screenshot` field inside
        # metadata lands in model_extra and _extract_screenshot_url falls back
        # to it when the top-level screenshot is absent.
        stub_result = ScrapeResult(
            screenshot=None,
            metadata=ScrapeMetadata.model_validate(
                {"screenshot": "https://cdn.firecrawl.dev/shots/xyz.png"}
            ),
        )

        class StubClient:
            async def scrape(self, url: str, formats: list[str]) -> ScrapeResult:
                return stub_result

        with patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()):
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )
        assert resp.status_code == 200
        assert resp.json() == {"screenshot_url": "https://cdn.firecrawl.dev/shots/xyz.png"}

    def test_returns_signed_stored_screenshot_without_firecrawl(
        self, client: TestClient
    ) -> None:
        async def lookup(*_args: object, **_kwargs: object) -> str:
            return "screenshots/browser-html.png"

        class StubCache:
            def sign_screenshot_key(self, storage_key: str | None) -> str | None:
                assert storage_key == "screenshots/browser-html.png"
                return "https://signed.example.com/browser-html.png"

        class StubClient:
            async def scrape(self, url: str, formats: list[str]) -> object:
                raise AssertionError("cache hits must not call Firecrawl")

        with (
            patch("src.routes.frame._lookup_stored_screenshot_key", side_effect=lookup),
            patch("src.routes.frame.get_scrape_cache", return_value=StubCache()),
            patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()),
        ):
            resp = client.get(
                "/api/screenshot",
                params={
                    "url": "https://example.com/article",
                    "job_id": "11111111-1111-1111-1111-111111111111",
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "screenshot_url": "https://signed.example.com/browser-html.png"
        }

    def test_cache_miss_falls_back_to_firecrawl(self, client: TestClient) -> None:
        from src.firecrawl_client import ScrapeResult

        async def lookup(*_args: object, **_kwargs: object) -> None:
            return None

        calls: list[str] = []
        stub_result = ScrapeResult(screenshot="https://cdn.firecrawl.dev/shots/miss.png")

        class StubClient:
            async def scrape(self, url: str, formats: list[str]) -> ScrapeResult:
                calls.append(url)
                return stub_result

        with (
            patch("src.routes.frame._lookup_stored_screenshot_key", side_effect=lookup),
            patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()),
        ):
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )

        assert resp.status_code == 200
        assert resp.json() == {"screenshot_url": "https://cdn.firecrawl.dev/shots/miss.png"}
        assert calls == ["https://example.com/article"]

    def test_signing_failure_falls_back_to_firecrawl(self, client: TestClient) -> None:
        from src.firecrawl_client import ScrapeResult

        async def lookup(*_args: object, **_kwargs: object) -> str:
            return "screenshots/stale.png"

        calls: list[str] = []
        stub_result = ScrapeResult(screenshot="https://cdn.firecrawl.dev/shots/fallback.png")

        class StubCache:
            def sign_screenshot_key(self, storage_key: str | None) -> None:
                assert storage_key == "screenshots/stale.png"

        class StubClient:
            async def scrape(self, url: str, formats: list[str]) -> ScrapeResult:
                calls.append(url)
                return stub_result

        with (
            patch("src.routes.frame._lookup_stored_screenshot_key", side_effect=lookup),
            patch("src.routes.frame.get_scrape_cache", return_value=StubCache()),
            patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()),
        ):
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "screenshot_url": "https://cdn.firecrawl.dev/shots/fallback.png"
        }
        assert calls == ["https://example.com/article"]

    def test_invalid_job_id_returns_400(self, client: TestClient) -> None:
        resp = client.get(
            "/api/screenshot",
            params={"url": "https://example.com/article", "job_id": "not-a-uuid"},
        )

        assert resp.status_code == 400
        assert resp.json() == {"detail": "Invalid job_id"}

    def test_firecrawl_blocked_returns_404_unsupported_site(
        self, client: TestClient
    ) -> None:
        from src.firecrawl_client import FirecrawlBlocked

        class StubClient:
            async def scrape(self, url: str, formats: list[str]) -> object:
                raise FirecrawlBlocked("firecrawl /v2/scrape refused: unsupported site")

        with patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()):
            resp = client.get(
                "/api/screenshot", params={"url": "https://reddit.com/r/example"}
            )

        assert resp.status_code == 404
        assert resp.json() == {
            "detail": "Site not supported",
            "reason": "unsupported_site",
        }

    def test_missing_screenshot_returns_404_no_screenshot(
        self, client: TestClient
    ) -> None:
        from src.firecrawl_client import ScrapeResult

        stub_result = ScrapeResult(screenshot=None, metadata=None)

        class StubClient:
            async def scrape(self, url: str, formats: list[str]) -> ScrapeResult:
                return stub_result

        with patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()):
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )
        assert resp.status_code == 404
        assert resp.json() == {
            "detail": "No screenshot available",
            "reason": "no_screenshot",
        }

    def test_transport_error_still_returns_502(self, client: TestClient) -> None:
        class StubClient:
            async def scrape(self, url: str, formats: list[str]) -> object:
                raise httpx.ConnectError("connection failed")

        with patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()):
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )

        assert resp.status_code == 502
        assert resp.json() == {"detail": "Screenshot service failed"}

    def test_screenshot_request_budget_bounds_slow_firecrawl(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class SlowClient:
            async def scrape(self, url: str, formats: list[str]) -> object:
                await asyncio.sleep(0.2)
                return {"screenshot": "https://cdn.firecrawl.dev/shots/late.png"}

        monkeypatch.setattr("src.routes.frame._SCREENSHOT_REQUEST_BUDGET_SECONDS", 0.01, raising=False)
        with patch("src.routes.frame.get_firecrawl_client", return_value=SlowClient()):
            started = time.monotonic()
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )
        assert time.monotonic() - started < 0.15
        assert resp.status_code == 502
        assert resp.json() == {"detail": "Screenshot service failed"}

    def test_invalid_url_returns_400(self, client: TestClient) -> None:
        resp = client.get("/api/screenshot", params={"url": "javascript:alert(1)"})
        assert resp.status_code == 400
        # Same human-readable detail as /api/frame-compat — the SSRF guard is
        # shared, so the screenshot route must surface the same copy clients
        # have been pinning since before the SSRF refactor.
        assert resp.json() == {"detail": "URL must be an http(s) URL"}


_SPA_SHAPED_CACHED_HTML = (
    "<!doctype html><html><body>"
    "<div id='spa'>"
    "  <div class='column'>"
    "    <div class='search'><h4>Recent searches</h4>"
    "      <p>No recent searches</p></div>"
    "  </div>"
    "  <div class='column'>"
    "    <div class='banner'>"
    "      <p><strong>example.social</strong> is one of the many "
    "         independent Mastodon servers you can use to participate "
    "         in the fediverse.</p>"
    "      <h4>Server stats:</h4>"
    "      <p><strong>2.4K</strong> active users</p>"
    "    </div>"
    "  </div>"
    "  <div class='column'>"
    "    <h1>Back</h1>"
    "    <article class='status'>"
    "      <header><strong>Author Name</strong> @author</header>"
    "      <div class='status__content'>"
    "        <p>Today's threads (a thread)</p>"
    "        <p>Inside: an investigation into chrome offset bugs and the "
    "           several paragraphs of substantive post body that should "
    "           appear in the archive viewport ahead of any nav or banner "
    "           text from the surrounding SPA shell.</p>"
    "        <p>The 2026 Guelph Lecture on enshittification will explore "
    "           how we can fix the internet by giving users back control. "
    "           This paragraph is here so the extracted main content "
    "           clears the substantial-content threshold comfortably.</p>"
    "      </div>"
    "    </article>"
    "  </div>"
    "</div>"
    "</body></html>"
)


class TestArchivePreview:
    def test_archive_preview_extracts_main_content_for_spa_shaped_html(
        self, client: TestClient
    ) -> None:
        # TASK-1577.02: archive iframe for SPA-served pages must surface
        # the post text ahead of site chrome. The route now runs
        # extract_archive_main_content on cached.html before falling
        # back to strip_for_display.
        from src.cache.scrape_cache import CachedScrape

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                if tier in {"browser_html", "interact"}:
                    return None
                return CachedScrape(html=_SPA_SHAPED_CACHED_HTML)

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.social/@author/123"},
            )

        assert resp.status_code == 200
        post_idx = resp.text.find("Today's threads")
        chrome_idx = resp.text.find("Server stats")
        recent_idx = resp.text.find("Recent searches")
        assert post_idx > 0, "post text missing from archive response"
        assert chrome_idx == -1 or post_idx < chrome_idx
        assert recent_idx == -1 or post_idx < recent_idx

    def test_archive_preview_uses_strip_when_extraction_loses_utterances(
        self, client: TestClient
    ) -> None:
        # TASK-1577.02 / Codex P1.2: when the analyze pipeline produced
        # utterances and the trafilatura extraction would drop one or more
        # of them, the route falls back to strip_for_display so the
        # per-utterance annotations don't silently disappear from the
        # archived view. Cached HTML below contains the utterance text;
        # we monkey-patch the extractor to return content that does NOT.
        from src.cache.scrape_cache import CachedScrape
        from src.utterances.schema import Utterance

        original_html = (
            "<!doctype html><html><body><main>"
            "<article><p>Alice opens calmly.</p></article>"
            "<section aria-label='Comments'><article class='comment'>"
            "<p>This comment is a forum reply that the analyze pipeline "
            "marked as an utterance.</p></article></section></main></body></html>"
        )
        # Extracted version drops the comment block (simulating trafilatura
        # over-stripping) — long enough to clear the 200-char threshold.
        extraction_without_utterance = (
            "<html><body><article>" + ("<p>Alice opens calmly.</p>" * 30)
            + "</article></body></html>"
        )

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                if tier in {"browser_html", "interact"}:
                    return None
                return CachedScrape(html=original_html)

        async def stub_lookup(
            pool: object, job_id: object, requested_url: str
        ) -> list[Utterance]:
            return [
                Utterance(
                    utterance_id="comment-1",
                    kind="comment",
                    text="This comment is a forum reply that the analyze pipeline marked as an utterance.",
                )
            ]

        from src.utils import html_sanitize as _hs

        _hs.extract_archive_main_content.cache_clear()  # type: ignore[attr-defined]

        _client_state(client).db_pool = object()
        try:
            with (
                patch("src.routes.frame.get_scrape_cache", return_value=StubCache()),
                patch(
                    "src.routes.frame.get_utterances_for_archive",
                    side_effect=stub_lookup,
                    create=True,
                ),
                patch(
                    "src.utils.html_sanitize.extract_archive_main_content.__wrapped__",
                    return_value=extraction_without_utterance,
                ),
            ):
                _hs.extract_archive_main_content.cache_clear()  # type: ignore[attr-defined]
                resp = client.get(
                    "/api/archive-preview",
                    params={
                        "url": "https://example.com/article",
                        "job_id": "11111111-1111-1111-1111-111111111111",
                    },
                )
        finally:
            del _client_state(client).db_pool
            _hs.extract_archive_main_content.cache_clear()  # type: ignore[attr-defined]

        assert resp.status_code == 200
        # Strip path was used → the comment text (and its annotation) survives.
        assert 'data-utterance-id="comment-1"' in resp.text
        assert "This comment is a forum reply" in resp.text

    def test_archive_preview_falls_back_to_strip_when_extractor_under_threshold(
        self, client: TestClient
    ) -> None:
        # When trafilatura yields content shorter than the substantial-content
        # threshold and there is no markdown to render, the route falls back
        # to the existing strip_for_display path so non-SPA pages keep
        # working. Asserts via response text content rather than cache call
        # bookkeeping (state-over-interactions per writing-better-tests).
        from src.cache.scrape_cache import CachedScrape

        small_html = "<html><body><p>tiny</p></body></html>"

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                if tier in {"browser_html", "interact"}:
                    return None
                return CachedScrape(html=small_html)

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/tiny"},
            )

        assert resp.status_code == 200
        # `strip_for_display` round-trips the body through bs4 — the literal
        # `<p>tiny</p>` survives intact.
        assert "<p>tiny</p>" in resp.text

    def test_cached_interact_html_served_when_scrape_tier_is_superficially_ok(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape
        from src.jobs.scrape_quality import ScrapeQuality, classify_scrape

        calls: list[str] = []

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                assert url == "https://example.com/article"
                calls.append(tier)
                if tier == "browser_html":
                    return None
                if tier == "scrape":
                    return CachedScrape(
                        html="<main><h1>Scrape preview</h1></main>",
                        raw_html="<script>bad()</script>",
                    )
                return CachedScrape(
                    html="<main><h1>Interact preview</h1></main>",
                    raw_html="<script>bad()</script>",
                )

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/article"},
            )

        assert (
            classify_scrape(CachedScrape(html="<main><h1>Scrape preview</h1></main>"))
            is ScrapeQuality.OK
        )
        assert resp.status_code == 200
        assert "Scrape preview" not in resp.text
        assert "Interact preview" in resp.text
        assert calls == ["interact"]

    def test_cached_browser_html_job_served_to_archive_preview(
        self, client: TestClient
    ) -> None:
        job_id = "22222222-2222-2222-2222-222222222222"

        class StubConn:
            async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
                assert "vibecheck_scrapes" in query
                assert args == (
                    UUID(job_id),
                    "https://example.com/extension-submitted",
                )
                return {
                    "url": "https://example.com/extension-submitted",
                    "final_url": "https://example.com/extension-submitted",
                    "page_title": "Extension archive",
                    "markdown": "Extension archive",
                    "html": "<main><h1>Extension archive</h1></main>",
                    "screenshot_storage_key": None,
                }

        class StubCache:
            async def get(self, url: str, *, tier: str = "scrape") -> None:
                raise AssertionError("browser_html lookup must be job-scoped")

        _client_state(client).db_pool = _FakePool(StubConn())
        try:
            with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
                resp = client.get(
                    "/api/archive-preview",
                    params={
                        "url": "https://example.com/extension-submitted",
                        "job_id": job_id,
                    },
                )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/html; charset=utf-8"
        assert "Extension archive" in resp.text

    def test_browser_html_archive_preview_is_scoped_by_job_id(
        self, client: TestClient
    ) -> None:
        first_job_id = UUID("33333333-3333-3333-3333-333333333333")
        second_job_id = UUID("44444444-4444-4444-4444-444444444444")
        rows: dict[UUID, dict[str, Any]] = {
            first_job_id: {
                "url": "https://example.com/repeated",
                "final_url": "https://example.com/repeated",
                "page_title": "First archive",
                "markdown": "First archive",
                "html": "<main><h1>First archive</h1></main>",
                "screenshot_storage_key": None,
            },
            second_job_id: {
                "url": "https://example.com/repeated",
                "final_url": "https://example.com/repeated",
                "page_title": "Second archive",
                "markdown": "Second archive",
                "html": "<main><h1>Second archive</h1></main>",
                "screenshot_storage_key": None,
            },
        }

        class StubConn:
            async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
                assert "vibecheck_scrapes" in query
                assert args[1] == "https://example.com/repeated"
                return rows.get(cast(UUID, args[0]))

        class StubCache:
            async def get(self, url: str, *, tier: str = "scrape") -> None:
                raise AssertionError("browser_html lookup must be job-scoped")

        _client_state(client).db_pool = _FakePool(StubConn())
        try:
            with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
                first = client.get(
                    "/api/archive-preview",
                    params={
                        "url": "https://example.com/repeated",
                        "job_id": str(first_job_id),
                    },
                )
                second = client.get(
                    "/api/archive-preview",
                    params={
                        "url": "https://example.com/repeated",
                        "job_id": str(second_job_id),
                    },
                )
        finally:
            del _client_state(client).db_pool

        assert first.status_code == 200
        assert "First archive" in first.text
        assert "Second archive" not in first.text
        assert second.status_code == 200
        assert "Second archive" in second.text
        assert "First archive" not in second.text

    def test_cached_interact_html_served_when_scrape_tier_is_non_ok(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape

        calls: list[str] = []

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                assert url == "https://example.com/article"
                calls.append(tier)
                if tier == "browser_html":
                    return None
                if tier == "scrape":
                    return CachedScrape(html="<main>Just a moment</main>")
                return CachedScrape(html="<main><h1>Interact preview</h1></main>")

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/article"},
            )

        assert resp.status_code == 200
        assert "Interact preview" in resp.text
        assert "Just a moment" not in resp.text
        assert calls == ["interact"]

    def test_cached_scrape_html_served_when_interact_tier_is_non_ok(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape

        calls: list[str] = []

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                assert url == "https://example.com/article"
                calls.append(tier)
                if tier == "browser_html":
                    return None
                if tier == "interact":
                    return CachedScrape(html="<main>Just a moment</main>")
                return CachedScrape(html="<main><h1>Scrape preview</h1></main>")

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/article"},
            )

        assert resp.status_code == 200
        assert "Scrape preview" in resp.text
        assert "Just a moment" not in resp.text
        assert calls == ["interact", "scrape"]

    def test_cached_scrape_html_served_for_interact_tier_when_scrape_empty(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape

        calls: list[str] = []

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                assert url == "https://example.com/fallback"
                calls.append(tier)
                if tier == "browser_html":
                    return None
                if tier == "scrape":
                    return None
                return CachedScrape(html="<main><h1>Interact preview</h1></main>")

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/fallback"},
            )

        assert resp.status_code == 200
        assert "Interact preview" in resp.text
        assert calls == ["interact"]

    def test_archive_preview_eviction_uses_served_tier_for_invalid_final_url(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape
        from src.firecrawl_client import ScrapeMetadata

        calls: list[tuple[str, str]] = []

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape | None:
                if tier == "browser_html":
                    return None
                if tier == "scrape":
                    return None
                return CachedScrape(
                    html="<main><p>Unsafe</p></main>",
                    metadata=ScrapeMetadata(source_url="file:///etc/passwd"),
                )

            def evict(self, url: str, *, tier: str) -> None:
                calls.append((url, tier))

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/unsafe"},
            )

        assert resp.status_code == 400
        assert resp.json() == {"detail": "URL must be an http(s) URL"}
        assert calls == [("https://example.com/unsafe", "interact")]

    def test_returns_cached_sanitized_html_with_restrictive_headers(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape:
                assert url == "https://example.com/article"
                if tier == "interact":
                    return CachedScrape(
                        html="<main><h1>Archived preview</h1></main>",
                        raw_html="<script>alert(1)</script>",
                    )
                return CachedScrape(
                    html="<main><h1>Archived preview</h1></main>",
                    raw_html="<script>alert(1)</script>",
                )

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/article"},
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/html; charset=utf-8"
        assert resp.headers["cache-control"] == "no-store, private"
        assert resp.headers["content-security-policy"] == (
            "default-src 'none'; img-src https: data:; "
            "style-src 'unsafe-inline' https:; font-src https: data:; "
            "frame-src 'none'; form-action 'none'; base-uri 'none'; "
            "frame-ancestors 'self'"
        )
        assert "Archived preview" in resp.text
        assert "alert(1)" not in resp.text

    def test_cached_html_with_matching_job_id_returns_annotated_html(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape
        from src.utterances.schema import Utterance

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape:
                assert url == "https://example.com/article"
                if tier == "interact":
                    return CachedScrape(html="<main><p>Alice opens calmly.</p></main>")
                return CachedScrape(html="<main><p>Alice opens calmly.</p></main>")

        async def stub_lookup(
            pool: object, job_id: object, requested_url: str
        ) -> list[Utterance]:
            assert pool is _client_state(client).db_pool
            assert requested_url == "https://example.com/article"
            return [
                Utterance(
                    utterance_id="comment-0-aaa",
                    kind="comment",
                    text="Alice opens calmly.",
                )
            ]

        _client_state(client).db_pool = object()
        try:
            with (
                patch("src.routes.frame.get_scrape_cache", return_value=StubCache()),
                patch(
                    "src.routes.frame.get_utterances_for_archive",
                    side_effect=stub_lookup,
                    create=True,
                ),
            ):
                resp = client.get(
                    "/api/archive-preview",
                    params={
                        "url": "https://example.com/article",
                        "job_id": "11111111-1111-1111-1111-111111111111",
                    },
                )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 200
        assert 'data-utterance-id="comment-0-aaa"' in resp.text

    def test_coral_archive_html_with_comment_utterances_returns_annotated_markers(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape
        from src.utterances.schema import Utterance

        coral_html = (
            '<main><section aria-label="Comments" data-coral-comments="true">'
            "<article class=\"comment\"><p>Small print matters.</p></article>"
            "</section></main>"
        )

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape:
                if tier == "interact":
                    return CachedScrape(html=coral_html)
                return CachedScrape(html=coral_html)

        async def stub_lookup(
            pool: object, job_id: object, requested_url: str
        ) -> list[Utterance]:
            return [
                Utterance(
                    utterance_id="comment-36-bcec4f13",
                    kind="comment",
                    text="Small print matters.",
                )
            ]

        _client_state(client).db_pool = object()
        try:
            with (
                patch("src.routes.frame.get_scrape_cache", return_value=StubCache()),
                patch(
                    "src.routes.frame.get_utterances_for_archive",
                    side_effect=stub_lookup,
                    create=True,
                ),
            ):
                resp = client.get(
                    "/api/archive-preview",
                    params={
                        "url": "https://latimes.example.com/coral-article",
                        "job_id": "f4646c83-add2-4a54-ac8a-38f2d31f51ea",
                    },
                )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 200
        assert 'data-coral-comments="true"' in resp.text
        assert 'data-utterance-id="comment-36-bcec4f13"' in resp.text

    def test_cached_html_without_job_id_preserves_unannotated_response(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape:
                return CachedScrape(html="<main><p>Alice opens calmly.</p></main>")

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/article"},
            )

        assert resp.status_code == 200
        assert "data-utterance-id" not in resp.text

    def test_pdf_archive_preview_returns_annotated_html_without_url_param(
        self, client: TestClient
    ) -> None:
        from src.utterances.schema import Utterance

        job_id = "11111111-1111-4111-8111-111111111111"
        gcs_key = "22222222-2222-4222-8222-222222222222"

        class Conn:
            async def fetchrow(self, query: str, received_job_id: object) -> dict[str, str]:
                assert "vibecheck_pdf_archives" in query
                assert str(received_job_id) == job_id
                return {
                    "html": "<main><p>Alice opens calmly.</p></main>",
                    "gcs_key": gcs_key,
                }

        async def stub_lookup(
            pool: object, received_job_id: object, requested_url: str
        ) -> list[Utterance]:
            assert pool is _client_state(client).db_pool
            assert str(received_job_id) == job_id
            assert requested_url == gcs_key
            return [
                Utterance(
                    utterance_id="pdf-utterance-1",
                    kind="post",
                    text="Alice opens calmly.",
                )
            ]

        _client_state(client).db_pool = _FakePool(Conn())
        try:
            with (
                patch("src.routes.frame.get_scrape_cache", side_effect=AssertionError),
                patch(
                    "src.routes.frame.get_utterances_for_archive",
                    side_effect=stub_lookup,
                    create=True,
                ),
            ):
                resp = client.get(
                    "/api/archive-preview",
                    params={"job_id": job_id, "source_type": "pdf"},
                )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-store, private"
        assert 'data-utterance-id="pdf-utterance-1"' in resp.text

    def test_pdf_archive_preview_missing_archive_returns_404(
        self, client: TestClient
    ) -> None:
        class Conn:
            async def fetchrow(self, query: str, received_job_id: object) -> None:
                return None

        _client_state(client).db_pool = _FakePool(Conn())
        try:
            resp = client.get(
                "/api/archive-preview",
                params={
                    "job_id": "11111111-1111-4111-8111-111111111111",
                    "source_type": "pdf",
                },
            )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 404
        assert resp.json() == {"detail": "Archive unavailable"}

    def test_pdf_read_redirects_to_fresh_signed_url(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id = "11111111-1111-4111-8111-111111111111"
        gcs_key = "22222222-2222-4222-8222-222222222222"

        class Conn:
            async def fetchval(self, query: str, received_job_id: object) -> str:
                assert "j.source_type = 'pdf'" in query
                assert "vibecheck_pdf_archives" in query
                assert "a.expires_at > now()" in query
                assert str(received_job_id) == job_id
                return gcs_key

        class Store:
            def __init__(self, bucket_name: str) -> None:
                assert bucket_name == "pdf-bucket"

            def signed_read_url(
                self, key: str, *, ttl_seconds: int = 900
            ) -> str:
                assert key == gcs_key
                assert ttl_seconds == 900
                return "https://storage.googleapis.com/pdf-bucket/read-signed"

        monkeypatch.setattr(
            "src.routes.frame.get_settings",
            lambda: SimpleNamespace(VIBECHECK_PDF_UPLOAD_BUCKET="pdf-bucket"),
        )
        monkeypatch.setattr("src.routes.frame.get_pdf_upload_store", Store)
        _client_state(client).db_pool = _FakePool(Conn())
        try:
            resp = client.get(
                "/api/pdf-read", params={"job_id": job_id}, follow_redirects=False
            )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 302
        assert (
            resp.headers["location"]
            == "https://storage.googleapis.com/pdf-bucket/read-signed"
        )
        assert resp.headers["cache-control"] == "no-store, private"
        assert resp.headers["referrer-policy"] == "no-referrer"

    def test_pdf_read_rejects_missing_pdf_job(self, client: TestClient) -> None:
        class Conn:
            async def fetchval(self, query: str, received_job_id: object) -> None:
                return None

        _client_state(client).db_pool = _FakePool(Conn())
        try:
            resp = client.get(
                "/api/pdf-read",
                params={"job_id": "11111111-1111-4111-8111-111111111111"},
            )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 404
        assert resp.json() == {"detail": "PDF unavailable"}

    def test_pdf_read_rejects_non_gcs_signed_url(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id = "11111111-1111-4111-8111-111111111111"
        gcs_key = "22222222-2222-4222-8222-222222222222"

        class Conn:
            async def fetchval(self, query: str, received_job_id: object) -> str:
                return gcs_key

        class Store:
            def __init__(self, bucket_name: str) -> None:
                pass

            def signed_read_url(
                self, key: str, *, ttl_seconds: int = 900
            ) -> str:
                return "https://evil.example.com/foo"

        monkeypatch.setattr(
            "src.routes.frame.get_settings",
            lambda: SimpleNamespace(VIBECHECK_PDF_UPLOAD_BUCKET="pdf-bucket"),
        )
        monkeypatch.setattr("src.routes.frame.get_pdf_upload_store", Store)
        _client_state(client).db_pool = _FakePool(Conn())
        try:
            resp = client.get(
                "/api/pdf-read", params={"job_id": job_id}, follow_redirects=False
            )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 502
        assert resp.json() == {"detail": "PDF unavailable"}

    def test_pdf_read_accepts_storage_cloud_google_com_url(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id = "11111111-1111-4111-8111-111111111111"
        gcs_key = "22222222-2222-4222-8222-222222222222"

        class Conn:
            async def fetchval(self, query: str, received_job_id: object) -> str:
                return gcs_key

        class Store:
            def __init__(self, bucket_name: str) -> None:
                pass

            def signed_read_url(
                self, key: str, *, ttl_seconds: int = 900
            ) -> str:
                return "https://storage.cloud.google.com/bucket/key"

        monkeypatch.setattr(
            "src.routes.frame.get_settings",
            lambda: SimpleNamespace(VIBECHECK_PDF_UPLOAD_BUCKET="pdf-bucket"),
        )
        monkeypatch.setattr("src.routes.frame.get_pdf_upload_store", Store)
        _client_state(client).db_pool = _FakePool(Conn())
        try:
            resp = client.get(
                "/api/pdf-read", params={"job_id": job_id}, follow_redirects=False
            )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 302
        assert (
            resp.headers["location"] == "https://storage.cloud.google.com/bucket/key"
        )

    def test_cached_html_with_mismatched_job_url_stays_unannotated(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape:
                return CachedScrape(html="<main><p>Alice opens calmly.</p></main>")

        async def stub_lookup(
            pool: object, job_id: object, requested_url: str
        ) -> list[object]:
            return []

        _client_state(client).db_pool = object()
        try:
            with (
                patch("src.routes.frame.get_scrape_cache", return_value=StubCache()),
                patch(
                    "src.routes.frame.get_utterances_for_archive",
                    side_effect=stub_lookup,
                    create=True,
                ),
            ):
                resp = client.get(
                    "/api/archive-preview",
                    params={
                        "url": "https://example.com/article",
                        "job_id": "11111111-1111-1111-1111-111111111111",
                    },
                )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 200
        assert "data-utterance-id" not in resp.text

    def test_cache_miss_without_generate_returns_archive_unavailable(
        self, client: TestClient
    ) -> None:
        calls: list[str] = []

        class StubCache:
            async def get(self, url: str, *, tier: str = "scrape") -> None:
                assert url == "https://example.com/miss"
                calls.append(tier)

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview", params={"url": "https://example.com/miss"}
            )
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Archive unavailable"}
        assert calls == ["interact", "scrape"]

    def test_cache_miss_without_generate_when_cached_tiers_are_unusable(
        self, client: TestClient
    ) -> None:
        calls: list[str] = []
        from src.cache.scrape_cache import CachedScrape

        class StubCache:
            async def get(self, url: str, *, tier: str = "scrape") -> CachedScrape | None:
                assert url == "https://example.com/unusable"
                calls.append(tier)
                if tier == "scrape":
                    return CachedScrape(html="<main>Just a moment</main>")
                return CachedScrape(html="<main>Checking your browser</main>")

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/unusable"},
            )

        assert resp.status_code == 404
        assert resp.json() == {"detail": "Archive unavailable"}
        assert calls == ["interact", "scrape"]

    def test_generate_scrapes_with_short_budget_and_stores_html(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape
        from src.firecrawl_client import ScrapeResult

        class StubCache:
            def __init__(self) -> None:
                self.put_url: str | None = None
                self.put_tier: str | None = None
                self.get_calls: list[str] = []

            async def get(self, url: str, *, tier: str = "scrape") -> None:
                assert url == "https://example.com/fresh"
                self.get_calls.append(tier)

            async def put(
                self,
                url: str,
                scrape: ScrapeResult,
                *,
                tier: str = "scrape",
            ) -> CachedScrape:
                self.put_url = url
                self.put_tier = tier
                return CachedScrape(html=scrape.html, metadata=scrape.metadata)

        class StubClient:
            async def scrape(
                self, url: str, formats: list[str], *, only_main_content: bool = False
            ) -> ScrapeResult:
                assert url == "https://example.com/fresh"
                assert formats == ["html", "markdown"]
                assert only_main_content is True
                return ScrapeResult(html="<article>Fresh archive</article>")

        cache = StubCache()
        with (
            patch("src.routes.frame.get_scrape_cache", return_value=cache),
            patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()),
        ):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/fresh", "generate": "1"},
        )
        assert resp.status_code == 200
        assert resp.text == (
            "<style>img{max-width:100%!important;height:auto!important}</style>"
            "<article>Fresh archive</article>"
        )
        assert cache.put_url == "https://example.com/fresh"
        assert cache.get_calls == ["interact", "scrape"]

    @pytest.mark.parametrize(
        ("html", "markdown"),
        [
            pytest.param(
                '<form action="/login"><input type="password"></form>',
                None,
                id="auth-wall",
            ),
            pytest.param("<main>Just a moment</main>", None, id="interstitial"),
            pytest.param("", "", id="empty"),
        ],
    )
    def test_generate_rejects_non_ok_scrapes_before_cache_write(
        self, client: TestClient, html: str, markdown: str | None
    ) -> None:
        from src.firecrawl_client import ScrapeResult

        class StubCache:
            def __init__(self) -> None:
                self.get_calls: list[str] = []

            async def get(self, url: str, *, tier: str = "scrape") -> None:
                assert url == "https://example.com/fresh-wall"
                self.get_calls.append(tier)

            async def put(self, *_args: object, **_kwargs: object) -> object:
                raise AssertionError("non-OK generated scrape must not be cached")

        class StubClient:
            async def scrape(
                self, url: str, formats: list[str], *, only_main_content: bool = False
            ) -> ScrapeResult:
                assert url == "https://example.com/fresh-wall"
                assert formats == ["html", "markdown"]
                assert only_main_content is True
                return ScrapeResult(html=html, markdown=markdown)

        cache = StubCache()
        with (
            patch("src.routes.frame.get_scrape_cache", return_value=cache),
            patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()),
        ):
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/fresh-wall", "generate": "1"},
            )

        assert resp.status_code == 502
        assert resp.json() == {"detail": "Archive unavailable"}
        assert cache.get_calls == ["interact", "scrape"]

    def test_generated_html_with_job_id_annotates_response_but_not_cache(
        self, client: TestClient
    ) -> None:
        from src.cache.scrape_cache import CachedScrape
        from src.firecrawl_client import ScrapeResult
        from src.utterances.schema import Utterance

        class StubCache:
            def __init__(self) -> None:
                self.stored_html: str | None = None

            async def get(self, url: str, *, tier: str = "scrape") -> None:
                return None

            async def put(
                self,
                url: str,
                scrape: ScrapeResult,
                *,
                tier: str = "scrape",
            ) -> CachedScrape:
                self.stored_html = scrape.html
                return CachedScrape(html=scrape.html, metadata=scrape.metadata)

        class StubClient:
            async def scrape(
                self, url: str, formats: list[str], *, only_main_content: bool = False
            ) -> ScrapeResult:
                return ScrapeResult(html="<article><p>Bob pushes back.</p></article>")

        async def stub_lookup(
            pool: object, job_id: object, requested_url: str
        ) -> list[Utterance]:
            return [
                Utterance(
                    utterance_id="comment-1-bbb",
                    kind="comment",
                    text="Bob pushes back.",
                )
            ]

        cache = StubCache()
        _client_state(client).db_pool = object()
        try:
            with (
                patch("src.routes.frame.get_scrape_cache", return_value=cache),
                patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()),
                patch(
                    "src.routes.frame.get_utterances_for_archive",
                    side_effect=stub_lookup,
                    create=True,
                ),
            ):
                resp = client.get(
                    "/api/archive-preview",
                    params={
                        "url": "https://example.com/fresh",
                        "generate": "1",
                        "job_id": "11111111-1111-1111-1111-111111111111",
                    },
                )
        finally:
            del _client_state(client).db_pool

        assert resp.status_code == 200
        assert 'data-utterance-id="comment-1-bbb"' in resp.text
        assert cache.stored_html == "<article><p>Bob pushes back.</p></article>"
        assert "data-utterance-id" not in (cache.stored_html or "")

    def test_generate_timeout_returns_archive_unavailable_quickly(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class StubCache:
            async def get(self, url: str, *, tier: str = "scrape") -> None:
                return None

        class SlowClient:
            async def scrape(self, url: str, formats: list[str], **kwargs: object) -> object:
                await asyncio.sleep(0.2)
                return object()

        monkeypatch.setattr("src.routes.frame._ARCHIVE_REQUEST_BUDGET_SECONDS", 0.01, raising=False)
        with (
            patch("src.routes.frame.get_scrape_cache", return_value=StubCache()),
            patch("src.routes.frame.get_firecrawl_client", return_value=SlowClient()),
        ):
            started = time.monotonic()
            resp = client.get(
                "/api/archive-preview",
                params={"url": "https://example.com/slow", "generate": "1"},
            )
        assert time.monotonic() - started < 0.15
        assert resp.status_code == 504
        assert resp.json() == {"detail": "Archive unavailable"}

    def test_invalid_url_returns_400(self, client: TestClient) -> None:
        resp = client.get("/api/archive-preview", params={"url": "file:///etc/passwd"})
        assert resp.status_code == 400
        assert resp.json() == {"detail": "URL must be an http(s) URL"}

    def test_invalid_job_id_returns_400_before_cache_lookup(
        self, client: TestClient
    ) -> None:
        class StubCache:
            async def get(self, url: str, *, tier: str = "scrape") -> object:
                raise AssertionError("cache should not be read for invalid job_id")

        with patch("src.routes.frame.get_scrape_cache", return_value=StubCache()):
            resp = client.get(
                "/api/archive-preview",
                params={
                    "url": "https://example.com/article",
                    "job_id": "not-a-uuid",
                },
            )

        assert resp.status_code == 400
        assert resp.json() == {"detail": "Invalid job_id"}


class TestSSRFValidation:
    def test_localhost_hostname_rejected(self, client: TestClient) -> None:
        resp = client.get("/api/frame-compat", params={"url": "http://localhost/admin"})
        assert resp.status_code == 400

    def test_metadata_hostname_rejected(self, client: TestClient) -> None:
        resp = client.get(
            "/api/frame-compat",
            params={"url": "http://metadata.google.internal/computeMetadata/v1/"},
        )
        assert resp.status_code == 400

    def test_internal_tld_rejected(self, client: TestClient) -> None:
        resp = client.get("/api/frame-compat", params={"url": "http://svc.internal/"})
        assert resp.status_code == 400

    def test_private_ip_resolution_rejected(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import socket

        def _resolve_to_private(
            *_args: object, **_kwargs: object
        ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", _resolve_to_private)
        resp = client.get("/api/frame-compat", params={"url": "http://evil.example.com/"})
        assert resp.status_code == 400
