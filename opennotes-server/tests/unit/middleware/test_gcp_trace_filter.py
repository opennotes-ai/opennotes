"""Unit tests for GCP trace header filter middleware."""

import os
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.middleware.gcp_trace_filter import (
    GCP_TRACE_HEADERS,
    GCPTraceHeaderFilter,
    wrap_app_with_gcp_trace_filter,
)


class TestGCPTraceHeaderFilter:
    """Tests for the GCPTraceHeaderFilter ASGI middleware."""

    @pytest.fixture
    def mock_app(self) -> AsyncMock:
        """Create a mock ASGI application."""
        return AsyncMock()

    @pytest.fixture
    def mock_receive(self) -> AsyncMock:
        """Create a mock receive callable."""
        return AsyncMock()

    @pytest.fixture
    def mock_send(self) -> AsyncMock:
        """Create a mock send callable."""
        return AsyncMock()

    def _create_http_scope(
        self,
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> dict[str, Any]:
        """Create an HTTP scope with optional headers."""
        return {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": headers or [],
        }

    @pytest.mark.asyncio
    async def test_strips_traceparent_header(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """Should strip the traceparent header from HTTP requests."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=True)
        scope = self._create_http_scope(
            headers=[
                (b"traceparent", b"00-trace-id-span-id-01"),
                (b"content-type", b"application/json"),
            ]
        )

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()
        called_scope = mock_app.call_args[0][0]
        header_names = [name for name, _ in called_scope["headers"]]
        assert b"traceparent" not in header_names
        assert b"content-type" in header_names

    @pytest.mark.asyncio
    async def test_strips_x_cloud_trace_context_header(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """Should strip the x-cloud-trace-context header."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=True)
        scope = self._create_http_scope(
            headers=[
                (b"x-cloud-trace-context", b"trace-id/span-id;o=1"),
                (b"authorization", b"Bearer token"),
            ]
        )

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()
        called_scope = mock_app.call_args[0][0]
        header_names = [name for name, _ in called_scope["headers"]]
        assert b"x-cloud-trace-context" not in header_names
        assert b"authorization" in header_names

    @pytest.mark.asyncio
    async def test_strips_grpc_trace_bin_header(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """Should strip the grpc-trace-bin header."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=True)
        scope = self._create_http_scope(
            headers=[
                (b"grpc-trace-bin", b"binary-trace-data"),
                (b"accept", b"*/*"),
            ]
        )

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()
        called_scope = mock_app.call_args[0][0]
        header_names = [name for name, _ in called_scope["headers"]]
        assert b"grpc-trace-bin" not in header_names
        assert b"accept" in header_names

    @pytest.mark.asyncio
    async def test_strips_all_gcp_headers_at_once(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """Should strip all GCP trace headers in a single request."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=True)
        scope = self._create_http_scope(
            headers=[
                (b"traceparent", b"00-trace-id-span-id-01"),
                (b"x-cloud-trace-context", b"trace-id/span-id;o=1"),
                (b"grpc-trace-bin", b"binary-trace-data"),
                (b"content-type", b"application/json"),
            ]
        )

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()
        called_scope = mock_app.call_args[0][0]
        header_names = [name for name, _ in called_scope["headers"]]
        assert b"traceparent" not in header_names
        assert b"x-cloud-trace-context" not in header_names
        assert b"grpc-trace-bin" not in header_names
        assert b"content-type" in header_names
        assert len(called_scope["headers"]) == 1

    @pytest.mark.asyncio
    async def test_case_insensitive_header_matching(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """Should strip headers regardless of case."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=True)
        scope = self._create_http_scope(
            headers=[
                (b"TraceParent", b"00-trace-id-span-id-01"),
                (b"X-CLOUD-TRACE-CONTEXT", b"trace-id/span-id;o=1"),
                (b"GRPC-Trace-Bin", b"binary-trace-data"),
                (b"Content-Type", b"application/json"),
            ]
        )

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()
        called_scope = mock_app.call_args[0][0]
        assert len(called_scope["headers"]) == 1
        assert called_scope["headers"][0][0] == b"Content-Type"

    @pytest.mark.asyncio
    async def test_preserves_non_gcp_headers(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """Should preserve all non-GCP trace headers."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=True)
        original_headers = [
            (b"content-type", b"application/json"),
            (b"authorization", b"Bearer token"),
            (b"x-request-id", b"req-123"),
            (b"user-agent", b"test-client"),
        ]
        scope = self._create_http_scope(headers=original_headers.copy())

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()
        called_scope = mock_app.call_args[0][0]
        assert called_scope["headers"] == original_headers

    @pytest.mark.asyncio
    async def test_disabled_does_not_strip_headers(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """When strip_headers=False, should pass through all headers unchanged."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=False)
        original_headers = [
            (b"traceparent", b"00-trace-id-span-id-01"),
            (b"content-type", b"application/json"),
        ]
        scope = self._create_http_scope(headers=original_headers.copy())

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()
        called_scope = mock_app.call_args[0][0]
        header_names = [name for name, _ in called_scope["headers"]]
        assert b"traceparent" in header_names

    @pytest.mark.asyncio
    async def test_websocket_scope_passes_through(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """WebSocket scopes should pass through unchanged."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=True)
        scope = {
            "type": "websocket",
            "path": "/ws",
            "headers": [
                (b"traceparent", b"00-trace-id-span-id-01"),
            ],
        }

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()
        called_scope = mock_app.call_args[0][0]
        assert called_scope["type"] == "websocket"
        header_names = [name for name, _ in called_scope["headers"]]
        assert b"traceparent" in header_names

    @pytest.mark.asyncio
    async def test_lifespan_scope_passes_through(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """Lifespan scopes should pass through unchanged."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=True)
        scope = {"type": "lifespan", "asgi": {"version": "3.0"}}

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()
        called_scope = mock_app.call_args[0][0]
        assert called_scope["type"] == "lifespan"

    @pytest.mark.asyncio
    async def test_empty_headers_handled(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """Should handle requests with no headers."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=True)
        scope = self._create_http_scope(headers=[])

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()
        called_scope = mock_app.call_args[0][0]
        assert called_scope["headers"] == []

    @pytest.mark.asyncio
    async def test_missing_headers_key_handled(
        self,
        mock_app: AsyncMock,
        mock_receive: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        """Should handle scope without headers key."""
        middleware = GCPTraceHeaderFilter(mock_app, strip_headers=True)
        scope = {"type": "http", "method": "GET", "path": "/test"}

        await middleware(scope, mock_receive, mock_send)

        mock_app.assert_called_once()


class TestGCPTraceHeaderFilterEnvConfig:
    """Tests for environment variable configuration."""

    @pytest.fixture
    def mock_app(self) -> AsyncMock:
        return AsyncMock()

    def test_defaults_to_enabled(self, mock_app: AsyncMock) -> None:
        """Should default to strip_headers=True when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            if "STRIP_GCP_TRACE_HEADERS" in os.environ:
                del os.environ["STRIP_GCP_TRACE_HEADERS"]
            middleware = GCPTraceHeaderFilter(mock_app)
            assert middleware.strip_headers is True

    def test_env_var_true(self, mock_app: AsyncMock) -> None:
        """Should enable when env var is 'true'."""
        with patch.dict(os.environ, {"STRIP_GCP_TRACE_HEADERS": "true"}):
            middleware = GCPTraceHeaderFilter(mock_app)
            assert middleware.strip_headers is True

    def test_env_var_1(self, mock_app: AsyncMock) -> None:
        """Should enable when env var is '1'."""
        with patch.dict(os.environ, {"STRIP_GCP_TRACE_HEADERS": "1"}):
            middleware = GCPTraceHeaderFilter(mock_app)
            assert middleware.strip_headers is True

    def test_env_var_yes(self, mock_app: AsyncMock) -> None:
        """Should enable when env var is 'yes'."""
        with patch.dict(os.environ, {"STRIP_GCP_TRACE_HEADERS": "yes"}):
            middleware = GCPTraceHeaderFilter(mock_app)
            assert middleware.strip_headers is True

    def test_env_var_false(self, mock_app: AsyncMock) -> None:
        """Should disable when env var is 'false'."""
        with patch.dict(os.environ, {"STRIP_GCP_TRACE_HEADERS": "false"}):
            middleware = GCPTraceHeaderFilter(mock_app)
            assert middleware.strip_headers is False

    def test_env_var_0(self, mock_app: AsyncMock) -> None:
        """Should disable when env var is '0'."""
        with patch.dict(os.environ, {"STRIP_GCP_TRACE_HEADERS": "0"}):
            middleware = GCPTraceHeaderFilter(mock_app)
            assert middleware.strip_headers is False

    def test_explicit_param_overrides_env(self, mock_app: AsyncMock) -> None:
        """Explicit strip_headers param should override env var."""
        with patch.dict(os.environ, {"STRIP_GCP_TRACE_HEADERS": "true"}):
            middleware = GCPTraceHeaderFilter(mock_app, strip_headers=False)
            assert middleware.strip_headers is False


class TestWrapAppFunction:
    """Tests for the wrap_app_with_gcp_trace_filter helper function."""

    @pytest.fixture
    def mock_app(self) -> AsyncMock:
        return AsyncMock()

    def test_returns_filter_when_not_testing(self, mock_app: AsyncMock) -> None:
        """Should return wrapped app when not in test mode."""
        with patch.dict(os.environ, {"TESTING": "false"}):
            result = wrap_app_with_gcp_trace_filter(mock_app)
            assert isinstance(result, GCPTraceHeaderFilter)

    def test_returns_original_when_testing(self, mock_app: AsyncMock) -> None:
        """Should return original app when in test mode."""
        with patch.dict(os.environ, {"TESTING": "true"}):
            result = wrap_app_with_gcp_trace_filter(mock_app)
            assert result is mock_app

    def test_force_wrap_overrides_testing(self, mock_app: AsyncMock) -> None:
        """force_wrap=True should wrap even in test mode."""
        with patch.dict(os.environ, {"TESTING": "true"}):
            result = wrap_app_with_gcp_trace_filter(mock_app, force_wrap=True)
            assert isinstance(result, GCPTraceHeaderFilter)

    def test_passes_strip_headers_to_filter(self, mock_app: AsyncMock) -> None:
        """Should pass strip_headers param to the filter."""
        with patch.dict(os.environ, {"TESTING": "false"}):
            result = wrap_app_with_gcp_trace_filter(mock_app, strip_headers=False)
            assert isinstance(result, GCPTraceHeaderFilter)
            assert result.strip_headers is False


class TestGCPTraceHeadersConstant:
    """Tests for the GCP_TRACE_HEADERS constant."""

    def test_contains_traceparent(self) -> None:
        """Should include traceparent header."""
        assert b"traceparent" in GCP_TRACE_HEADERS

    def test_contains_x_cloud_trace_context(self) -> None:
        """Should include x-cloud-trace-context header."""
        assert b"x-cloud-trace-context" in GCP_TRACE_HEADERS

    def test_contains_grpc_trace_bin(self) -> None:
        """Should include grpc-trace-bin header."""
        assert b"grpc-trace-bin" in GCP_TRACE_HEADERS

    def test_all_headers_are_lowercase_bytes(self) -> None:
        """All header names should be lowercase bytes for matching."""
        for header in GCP_TRACE_HEADERS:
            assert isinstance(header, bytes)
            assert header == header.lower()
