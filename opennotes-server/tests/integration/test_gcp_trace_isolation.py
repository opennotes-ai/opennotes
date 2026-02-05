"""Integration tests for GCP trace context isolation.

Verifies that the GCPTraceHeaderFilter middleware correctly strips GCP-injected
trace headers, ensuring each HTTP request creates an independent trace rather
than being grouped under a shared GCP trace ID.
"""

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.middleware.gcp_trace_filter import GCPTraceHeaderFilter


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    """Create an in-memory span exporter for capturing traces."""
    return InMemorySpanExporter()


@pytest.fixture
def tracer_provider(span_exporter: InMemorySpanExporter) -> TracerProvider:
    """Create a tracer provider with in-memory exporter."""
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture
def test_app() -> FastAPI:
    """Create a test FastAPI app with a simple endpoint."""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint() -> dict[str, str]:
        current_span = trace.get_current_span()
        span_context = current_span.get_span_context()
        return {
            "trace_id": format(span_context.trace_id, "032x"),
            "span_id": format(span_context.span_id, "016x"),
        }

    return app


@pytest.fixture
def instrumented_app(
    test_app: FastAPI,
    tracer_provider: TracerProvider,
) -> FastAPI:
    """Instrument the test app with OpenTelemetry."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    original_provider = trace.get_tracer_provider()
    trace.set_tracer_provider(tracer_provider)

    FastAPIInstrumentor.instrument_app(test_app)

    yield test_app

    FastAPIInstrumentor.uninstrument_app(test_app)
    trace.set_tracer_provider(original_provider)


class TestGCPTraceIsolation:
    """Tests verifying trace isolation when GCP headers are present."""

    @pytest.mark.asyncio
    async def test_requests_without_traceparent_get_unique_trace_ids(
        self,
        instrumented_app: FastAPI,
        span_exporter: InMemorySpanExporter,
    ) -> None:
        """Requests without traceparent should each get unique trace IDs."""
        wrapped_app = GCPTraceHeaderFilter(instrumented_app, strip_headers=True)
        transport = ASGITransport(app=wrapped_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response1 = await client.get("/test")
            response2 = await client.get("/test")
            response3 = await client.get("/test")

        trace_id_1 = response1.json()["trace_id"]
        trace_id_2 = response2.json()["trace_id"]
        trace_id_3 = response3.json()["trace_id"]

        assert trace_id_1 != trace_id_2
        assert trace_id_2 != trace_id_3
        assert trace_id_1 != trace_id_3

    @pytest.mark.asyncio
    async def test_gcp_traceparent_is_stripped(
        self,
        instrumented_app: FastAPI,
    ) -> None:
        """Requests with GCP traceparent should NOT inherit that trace ID."""
        wrapped_app = GCPTraceHeaderFilter(instrumented_app, strip_headers=True)
        transport = ASGITransport(app=wrapped_app)

        gcp_trace_id = "0af7651916cd43dd8448eb211c80319c"
        gcp_traceparent = f"00-{gcp_trace_id}-b7ad6b7169203331-01"

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response1 = await client.get(
                "/test",
                headers={"traceparent": gcp_traceparent},
            )
            response2 = await client.get(
                "/test",
                headers={"traceparent": gcp_traceparent},
            )

        trace_id_1 = response1.json()["trace_id"]
        trace_id_2 = response2.json()["trace_id"]

        assert trace_id_1 != gcp_trace_id
        assert trace_id_2 != gcp_trace_id
        assert trace_id_1 != trace_id_2

    @pytest.mark.asyncio
    async def test_x_cloud_trace_context_is_stripped(
        self,
        instrumented_app: FastAPI,
    ) -> None:
        """Requests with X-Cloud-Trace-Context should NOT inherit that trace."""
        wrapped_app = GCPTraceHeaderFilter(instrumented_app, strip_headers=True)
        transport = ASGITransport(app=wrapped_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response1 = await client.get(
                "/test",
                headers={"x-cloud-trace-context": "trace-id-123/span-id;o=1"},
            )
            response2 = await client.get(
                "/test",
                headers={"x-cloud-trace-context": "trace-id-123/span-id;o=1"},
            )

        trace_id_1 = response1.json()["trace_id"]
        trace_id_2 = response2.json()["trace_id"]

        assert trace_id_1 != trace_id_2

    @pytest.mark.asyncio
    async def test_filter_disabled_allows_trace_propagation(
        self,
        instrumented_app: FastAPI,
    ) -> None:
        """When filter is disabled, traceparent should propagate (legacy behavior)."""
        wrapped_app = GCPTraceHeaderFilter(instrumented_app, strip_headers=False)
        transport = ASGITransport(app=wrapped_app)

        gcp_trace_id = "0af7651916cd43dd8448eb211c80319c"
        gcp_traceparent = f"00-{gcp_trace_id}-b7ad6b7169203331-01"

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/test",
                headers={"traceparent": gcp_traceparent},
            )

        trace_id = response.json()["trace_id"]
        assert trace_id == gcp_trace_id

    @pytest.mark.asyncio
    async def test_non_trace_headers_preserved(
        self,
        instrumented_app: FastAPI,
    ) -> None:
        """Non-trace headers should be preserved and accessible."""
        from starlette.requests import Request

        app = FastAPI()

        @app.get("/echo-headers")
        async def echo_headers(request: Request) -> dict[str, list[str]]:
            return {"headers": list(request.headers.keys())}

        wrapped_app = GCPTraceHeaderFilter(app, strip_headers=True)
        transport = ASGITransport(app=wrapped_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/echo-headers",
                headers={
                    "traceparent": "00-trace-id-span-id-01",
                    "x-custom-header": "custom-value",
                    "authorization": "Bearer token",
                    "content-type": "application/json",
                },
            )

        assert response.status_code == 200
        headers_received = response.json()["headers"]
        assert "x-custom-header" in headers_received
        assert "authorization" in headers_received
        assert "content-type" in headers_received
        assert "traceparent" not in headers_received


class TestGCPTraceFilterWithRealApp:
    """Tests using a more realistic app configuration."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests_isolated(
        self,
        instrumented_app: FastAPI,
    ) -> None:
        """Multiple concurrent requests should each get unique traces."""
        import asyncio

        wrapped_app = GCPTraceHeaderFilter(instrumented_app, strip_headers=True)
        transport = ASGITransport(app=wrapped_app)

        gcp_traceparent = "00-shared-gcp-trace-id-000000-span-id-01"

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            tasks = [
                client.get("/test", headers={"traceparent": gcp_traceparent}) for _ in range(10)
            ]
            responses = await asyncio.gather(*tasks)

        trace_ids = [r.json()["trace_id"] for r in responses]
        unique_trace_ids = set(trace_ids)

        assert len(unique_trace_ids) == 10

    @pytest.mark.asyncio
    async def test_env_var_controls_filter(self) -> None:
        """STRIP_GCP_TRACE_HEADERS env var should control filtering."""
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            current_span = trace.get_current_span()
            span_context = current_span.get_span_context()
            return {"trace_id": format(span_context.trace_id, "032x")}

        original_provider = trace.get_tracer_provider()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)

        try:
            with patch.dict(os.environ, {"STRIP_GCP_TRACE_HEADERS": "false"}):
                wrapped_app = GCPTraceHeaderFilter(app)

            assert wrapped_app.strip_headers is False

            with patch.dict(os.environ, {"STRIP_GCP_TRACE_HEADERS": "true"}):
                wrapped_app = GCPTraceHeaderFilter(app)

            assert wrapped_app.strip_headers is True
        finally:
            FastAPIInstrumentor.uninstrument_app(app)
            trace.set_tracer_provider(original_provider)
