"""
ASGI middleware to strip GCP-injected trace headers from incoming HTTP requests.

GCP Cloud Run automatically injects `traceparent` (W3C) and `X-Cloud-Trace-Context`
(legacy GCP format) headers into incoming requests. OpenTelemetry's FastAPIInstrumentor
extracts these headers and uses them as parent trace context, causing multiple unrelated
requests to be grouped under the same trace ID.

This middleware strips these headers BEFORE OpenTelemetry processes them, ensuring
each HTTP request starts a new root trace with an independent trace ID.

References:
- https://lynn.zone/blog/opting-out-of-tracing-on-gcp
- https://cloud.google.com/trace/docs/trace-context
- https://cloud.google.com/run/docs/trace
"""

import logging
import os

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

GCP_TRACE_HEADERS: set[bytes] = {
    b"traceparent",
    b"x-cloud-trace-context",
    b"grpc-trace-bin",
}


class GCPTraceHeaderFilter:
    """
    ASGI middleware that strips GCP-injected trace headers from incoming HTTP requests.

    This middleware runs at the ASGI level (outermost layer) to intercept headers
    before OpenTelemetry's instrumentation can extract them.

    Args:
        app: The wrapped ASGI application.
        strip_headers: Whether to strip GCP trace headers. If None, reads from
            STRIP_GCP_TRACE_HEADERS env var (defaults to True).
    """

    app: ASGIApp
    strip_headers: bool

    def __init__(self, app: ASGIApp, strip_headers: bool | None = None) -> None:
        self.app = app
        if strip_headers is None:
            env_value = os.getenv("STRIP_GCP_TRACE_HEADERS", "true")
            self.strip_headers = env_value.lower() in ("true", "1", "yes")
        else:
            self.strip_headers = strip_headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self.strip_headers:
            original_headers = scope.get("headers", [])
            filtered_headers = []
            stripped_count = 0

            for name, value in original_headers:
                if name.lower() in GCP_TRACE_HEADERS:
                    stripped_count += 1
                    logger.debug(
                        "Stripped GCP trace header: %s",
                        name.decode("latin-1", errors="replace"),
                    )
                else:
                    filtered_headers.append((name, value))

            if stripped_count > 0:
                scope = dict(scope)
                scope["headers"] = filtered_headers
                logger.debug(
                    "Stripped %d GCP trace header(s) from incoming request",
                    stripped_count,
                )

        await self.app(scope, receive, send)


def wrap_app_with_gcp_trace_filter(
    app: ASGIApp,
    *,
    strip_headers: bool | None = None,
    force_wrap: bool = False,
) -> ASGIApp:
    """
    Wrap an ASGI app with the GCP trace header filter.

    This function provides a convenient way to wrap an app and handles
    environment-based configuration.

    Args:
        app: The ASGI application to wrap.
        strip_headers: Whether to strip headers. Defaults to env var or True.
        force_wrap: If True, wrap even when TESTING=true. Used for tests.

    Returns:
        The wrapped application, or the original app if in test mode.
    """
    if not force_wrap:
        testing = os.getenv("TESTING", "false").lower() == "true"
        if testing:
            return app

    return GCPTraceHeaderFilter(app, strip_headers=strip_headers)
