"""Middleware.io APM integration for unified observability.

This module provides Middleware.io APM setup which replaces the legacy
OpenTelemetry/Pyroscope setup with a unified solution for:
- Distributed tracing
- Metrics collection
- Log aggregation
- Continuous profiling

IMPORTANT: Due to OpenTelemetry version constraints, the recommended approach
is to use the `middleware-run` wrapper for zero-code instrumentation rather
than the in-code SDK initialization.

Wrapper Approach (Recommended):
    Instead of running:
        uvicorn src.main:app --host 0.0.0.0 --port 8000

    Run with middleware-run wrapper:
        middleware-run uvicorn src.main:app --host 0.0.0.0 --port 8000

    Required environment variables:
        MW_API_KEY: Middleware.io API key
        MW_TARGET: OTLP endpoint (e.g., https://myaccount.middleware.io:443)
        MW_SERVICE_NAME: Service name (optional, defaults to app name)

In-Code Approach (requires middleware-io package):
    If you need in-code initialization, install middleware-io package and call
    setup_middleware_apm() BEFORE importing any instrumented libraries.

    Note: This may require downgrading OTel packages to match middleware-io
    requirements (0.57b0 instrumentation packages with 1.36.0 core).

Reference: https://docs.middleware.io/apm-configuration/python

Created: task-969
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_mw_initialized = False


def setup_middleware_apm(
    api_key: str,
    target: str,
    service_name: str,
    sample_rate: float = 1.0,
) -> bool:
    """Initialize Middleware.io APM using in-code SDK.

    IMPORTANT: This must be called BEFORE importing any libraries that need
    instrumentation (FastAPI, SQLAlchemy, Redis, etc.) for automatic
    instrumentation to work correctly.

    Note: The middleware-io package has strict OpenTelemetry version requirements
    (0.57b0 instrumentation, 1.36.0 core). If there are version conflicts with
    existing OTel packages, use the middleware-run wrapper approach instead.

    Args:
        api_key: Middleware.io API key
        target: Middleware.io OTLP endpoint
        service_name: Service name for identification
        sample_rate: Trace sampling rate (0.0-1.0), currently unused by MW SDK

    Returns:
        True if initialization succeeded, False otherwise
    """
    global _mw_initialized

    if _mw_initialized:
        logger.debug("Middleware.io APM already initialized")
        return True

    try:
        from middleware import MWOptions, mw_tracker  # type: ignore[import-not-found]

        mw_options = MWOptions(
            access_token=api_key,
            target=target,
            service_name=service_name,
        )

        mw_tracker(mw_options)
        _mw_initialized = True

        logger.info(
            f"Middleware.io APM initialized: service={service_name}, "
            f"target={target}, sample_rate={sample_rate}"
        )
        return True

    except ImportError:
        logger.warning(
            "middleware-io package not installed. Using middleware-run wrapper approach. "
            "If in-code init is needed, install with: uv add middleware-io "
            "(may require OTel version downgrades)"
        )
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Middleware.io APM: {e}")
        return False


def is_middleware_apm_configured() -> bool:
    """Check if Middleware.io APM environment variables are configured.

    This is useful to determine if MW APM should be used even when the
    middleware-io package is not installed (wrapper approach).

    Returns:
        True if MW_API_KEY and MW_TARGET are set, False otherwise
    """
    import os

    api_key = os.getenv("MW_API_KEY")
    target = os.getenv("MW_TARGET")
    return bool(api_key and target)


def get_middleware_apm_config() -> dict[str, str | float | None]:
    """Get Middleware.io APM configuration from environment variables.

    Returns:
        Dictionary with MW configuration values
    """
    import os

    return {
        "api_key": os.getenv("MW_API_KEY"),
        "target": os.getenv("MW_TARGET"),
        "service_name": os.getenv("MW_SERVICE_NAME"),
        "sample_rate": float(os.getenv("MW_SAMPLE_RATE", "1.0")),
        "enabled": os.getenv("MIDDLEWARE_APM_ENABLED", "false").lower() == "true",
    }
