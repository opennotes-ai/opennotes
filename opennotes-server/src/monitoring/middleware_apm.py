"""Middleware.io APM integration for unified observability.

This module provides Middleware.io APM setup which replaces the legacy
OpenTelemetry/Pyroscope setup with a unified solution for:
- Distributed tracing
- Metrics collection
- Log aggregation
- Continuous profiling

Usage:
    Set MIDDLEWARE_APM_ENABLED=true and provide MW_API_KEY, MW_TARGET
    environment variables. The APM is automatically initialized early
    in main.py before other imports for automatic instrumentation.

Alternative - Wrapper Approach:
    Instead of in-code init, run with middleware-run wrapper:
        middleware-run uvicorn src.main:app --host 0.0.0.0 --port 8000

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
    collect_profiling: bool = True,
    collect_metrics: bool = True,
    collect_logs: bool = True,
) -> bool:
    """Initialize Middleware.io APM using in-code SDK.

    IMPORTANT: This must be called BEFORE importing any libraries that need
    instrumentation (FastAPI, SQLAlchemy, Redis, etc.) for automatic
    instrumentation to work correctly.

    Args:
        api_key: Middleware.io API key
        target: Middleware.io OTLP endpoint
        service_name: Service name for identification
        sample_rate: Trace sampling rate (0.0-1.0)
        collect_profiling: Enable continuous profiling (requires middleware-io[profiling])
        collect_metrics: Enable metrics collection
        collect_logs: Enable log collection

    Returns:
        True if initialization succeeded, False otherwise
    """
    global _mw_initialized

    if _mw_initialized:
        logger.debug("Middleware.io APM already initialized")
        return True

    try:
        from middleware import MWOptions, mw_tracker

        sample_rate_int = int(sample_rate * 100) if sample_rate <= 1.0 else int(sample_rate)

        mw_options = MWOptions(
            access_token=api_key,
            target=target,
            service_name=service_name,
            sample_rate=sample_rate_int,
            collect_profiling=collect_profiling,
            collect_metrics=collect_metrics,
            collect_logs=collect_logs,
        )

        mw_tracker(mw_options)
        _mw_initialized = True

        features = []
        if collect_profiling:
            features.append("profiling")
        if collect_metrics:
            features.append("metrics")
        if collect_logs:
            features.append("logs")
        features_str = ", ".join(features) if features else "traces only"

        logger.info(
            f"Middleware.io APM initialized: service={service_name}, "
            f"target={target}, sample_rate={sample_rate}, features=[{features_str}]"
        )
        return True

    except ImportError:
        logger.error(
            "middleware-io package not installed. Install with: uv add 'middleware-io[profiling]'"
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


def get_middleware_apm_config() -> dict[str, str | float | bool | None]:
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
        "collect_profiling": os.getenv("MW_COLLECT_PROFILING", "true").lower() == "true",
        "collect_metrics": os.getenv("MW_COLLECT_METRICS", "true").lower() == "true",
        "collect_logs": os.getenv("MW_COLLECT_LOGS", "true").lower() == "true",
    }
