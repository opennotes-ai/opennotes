import asyncio
import time
from typing import Any, cast
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

from src.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _client_state(client: TestClient) -> Any:
    return cast(Any, client.app).state


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

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape:
                assert url == "https://archived.example.com/"
                assert tier == "scrape"
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

    def test_has_archive_checks_interact_tier_if_scrape_empty(
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
                if tier == "scrape":
                    return None
                return CachedScrape(html="<main>Interact archived</main>")

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
        assert calls == ["scrape", "interact"]

    def test_has_archive_still_true_for_non_ok_tier_one_html(
        self, client: TestClient, httpx_mock: HTTPXMock
    ) -> None:
        from src.cache.scrape_cache import CachedScrape

        class StubCache:
            async def get(
                self, url: str, *, tier: str = "scrape"
            ) -> CachedScrape:
                assert url == "https://interstitial-archive.example.com/"
                assert tier == "scrape"
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
        assert resp.json()["has_archive"] is True

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
        assert calls == ["scrape", "interact"]

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

    def test_missing_screenshot_returns_502(self, client: TestClient) -> None:
        from src.firecrawl_client import ScrapeResult

        stub_result = ScrapeResult(screenshot=None, metadata=None)

        class StubClient:
            async def scrape(self, url: str, formats: list[str]) -> ScrapeResult:
                return stub_result

        with patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()):
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )
        assert resp.status_code == 502

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


class TestArchivePreview:
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
                assert formats == ["html"]
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
        assert resp.text == "<article>Fresh archive</article>"
        assert cache.put_url == "https://example.com/fresh"
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
