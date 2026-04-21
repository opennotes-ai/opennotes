from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

from src.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


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


class TestScreenshot:
    def test_returns_screenshot_url(self, client: TestClient) -> None:
        stub_result = MagicMock()
        stub_result.screenshot = "https://cdn.firecrawl.dev/shots/abc.png"
        stub_result.metadata = None

        class StubClient:
            def scrape(self, url: str, formats: list[str]) -> MagicMock:
                return stub_result

        with patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()):
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )
        assert resp.status_code == 200
        assert resp.json() == {"screenshot_url": "https://cdn.firecrawl.dev/shots/abc.png"}

    def test_falls_back_to_metadata_screenshot(self, client: TestClient) -> None:
        stub_result = MagicMock()
        stub_result.screenshot = None
        stub_result.metadata = {"screenshot": "https://cdn.firecrawl.dev/shots/xyz.png"}

        class StubClient:
            def scrape(self, url: str, formats: list[str]) -> MagicMock:
                return stub_result

        with patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()):
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )
        assert resp.status_code == 200
        assert resp.json() == {"screenshot_url": "https://cdn.firecrawl.dev/shots/xyz.png"}

    def test_missing_screenshot_returns_502(self, client: TestClient) -> None:
        stub_result = MagicMock()
        stub_result.screenshot = None
        stub_result.metadata = {}

        class StubClient:
            def scrape(self, url: str, formats: list[str]) -> MagicMock:
                return stub_result

        with patch("src.routes.frame.get_firecrawl_client", return_value=StubClient()):
            resp = client.get(
                "/api/screenshot", params={"url": "https://example.com/article"}
            )
        assert resp.status_code == 502

    def test_invalid_url_returns_400(self, client: TestClient) -> None:
        resp = client.get("/api/screenshot", params={"url": "javascript:alert(1)"})
        assert resp.status_code == 400


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

        def _resolve_to_private(*_args: object, **_kwargs: object) -> list:
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", _resolve_to_private)
        resp = client.get("/api/frame-compat", params={"url": "http://evil.example.com/"})
        assert resp.status_code == 400
