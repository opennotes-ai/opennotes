"""Prometheus metrics for the vibecheck async pipeline (TASK-1473.15).

Cardinality is the dominant correctness concern for Prometheus metrics — a
single unbounded label set will explode the time-series database. Every
metric in this module uses bounded label sets:

- `slug` is bounded by the known `SectionSlug` enum members.
- `status` is the five-value `JobStatus` enum.
- `tier` is a small literal set (`scrape`, `analysis`).
- `error_type` is the four-value `_ERROR_BUCKETS` literal set produced by
  `classify_error`. Raw exception classes / hostnames / URLs / job_ids
  are NEVER used as labels; raw error detail is NEVER used as a label.

`classify_error` buckets exception classes into one of four families.
Subclasses inherit their parent's bucket: `httpx.TimeoutException` is
`upstream` → `timeout` because the timeout check runs first; new transport
exceptions land in `upstream` automatically.

All metrics are registered against the default global registry so the
ASGI app mounted at `/metrics` (see `src.main`) exposes them without
extra wiring.
"""
from __future__ import annotations

import asyncio
from typing import Literal

import httpx
from prometheus_client import Counter, Gauge, Histogram

__all__ = [
    "ACTIVE_JOBS",
    "CACHE_HITS",
    "CLOUD_TASKS_REDELIVERIES",
    "EXTERNAL_API_CALLS",
    "EXTERNAL_API_ERRORS",
    "EXTERNAL_API_FLAGGED",
    "EXTERNAL_API_LATENCY",
    "JOB_DURATION",
    "ORPHAN_SWEEPS",
    "SECTION_DURATION",
    "SECTION_FAILURES",
    "SECTION_MEDIA_DROPPED",
    "SINGLE_FLIGHT_LOCK_WAITS",
    "ErrorType",
    "ExternalAPI",
    "ExternalAPIErrorCategory",
    "classify_error",
]


ErrorType = Literal["timeout", "upstream", "extraction", "internal"]
ExternalAPI = Literal["webrisk", "gcp_nl", "vision", "factcheck", "video_intelligence"]
ExternalAPIErrorCategory = Literal[
    "none",
    "auth",
    "timeout",
    "rate_limited",
    "upstream",
    "network",
    "invalid_response",
    "invalid_image",
    "extraction",
    "internal",
]


JOB_DURATION = Histogram(
    "vibecheck_job_duration_seconds",
    "End-to-end duration of an async vibecheck job, by terminal status.",
    labelnames=("status",),
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0, 300.0),
)

SECTION_DURATION = Histogram(
    "vibecheck_section_duration_seconds",
    "Per-section analysis duration, by SectionSlug.",
    labelnames=("slug",),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0),
)

SECTION_FAILURES = Counter(
    "vibecheck_section_failures_total",
    "Per-section failures bucketed by classified error type.",
    labelnames=("slug", "error_type"),
)

CACHE_HITS = Counter(
    "vibecheck_cache_hits_total",
    "Cache hits by tier (scrape, analysis).",
    labelnames=("tier",),
)

ACTIVE_JOBS = Gauge(
    "vibecheck_active_jobs",
    "Number of jobs currently being processed by this worker.",
)

CLOUD_TASKS_REDELIVERIES = Counter(
    "vibecheck_cloud_tasks_redeliveries_total",
    "Cloud Tasks redeliveries that the orchestrator no-op'd via attempt_id CAS.",
)

ORPHAN_SWEEPS = Counter(
    "vibecheck_orphan_sweeps_total",
    "Orphan-job sweeps observed by the server. Pg_cron does the actual sweep.",
)

SINGLE_FLIGHT_LOCK_WAITS = Counter(
    "vibecheck_single_flight_lock_waits_total",
    "Times the POST /api/analyze advisory lock was contended on first attempt.",
)

EXTERNAL_API_CALLS = Counter(
    "vibecheck_external_api_calls_total",
    "External moderation/fact-check API calls by bounded provider name.",
    labelnames=("api",),
)

EXTERNAL_API_ERRORS = Counter(
    "vibecheck_external_api_errors_total",
    "External API errors by bounded provider and category.",
    labelnames=("api", "error_category"),
)

EXTERNAL_API_LATENCY = Histogram(
    "vibecheck_external_api_latency_seconds",
    "External API call latency by bounded provider name.",
    labelnames=("api",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0),
)

EXTERNAL_API_FLAGGED = Counter(
    "vibecheck_external_api_flagged_total",
    "Findings flagged by each external moderation/fact-check provider.",
    labelnames=("api",),
)

SECTION_MEDIA_DROPPED = Counter(
    "vibecheck_section_media_dropped_total",
    "Media URLs dropped by per-section caps.",
    labelnames=("media_type",),
)


_TERMINAL_ERROR_CODE_BUCKETS: dict[str, ErrorType] = {
    "extraction_failed": "extraction",
    "timeout": "timeout",
    "upstream_error": "upstream",
    "unsupported_site": "upstream",
}


def classify_error(exc: BaseException) -> ErrorType:
    """Bucket an exception class into one of four bounded labels.

    Order matters: `asyncio.TimeoutError` is also `OSError`, so the timeout
    check runs first. `httpx.TimeoutException` is checked before
    `httpx.HTTPError` for the same reason.

    Inspects orchestrator exceptions structurally via `type(exc).__name__`
    + a duck-typed `error_code.value` attribute lookup. Avoids the
    circular import that `from src.jobs.orchestrator import TerminalError`
    would create — `orchestrator.py` imports this module at the top
    level for metric handles.
    """
    if isinstance(exc, TimeoutError | asyncio.TimeoutError | httpx.TimeoutException):
        return "timeout"
    cls_name = type(exc).__name__
    if cls_name == "TerminalError":
        code_value = getattr(getattr(exc, "error_code", None), "value", None)
        if isinstance(code_value, str):
            return _TERMINAL_ERROR_CODE_BUCKETS.get(code_value, "internal")
        return "internal"
    if cls_name == "TransientError":
        return "upstream"
    if isinstance(exc, httpx.HTTPError | ConnectionError | OSError):
        return "upstream"
    return "internal"
