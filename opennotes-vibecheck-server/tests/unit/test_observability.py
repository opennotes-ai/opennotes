"""Tests for observability wiring (TASK-1473.15).

Exercises:
- contextvar binding makes `job_id` / `attempt_id` / `slug` appear on log records
- the sanitize filter strips Supabase signed-URL credentials before reaching the sink
- Prometheus counter labels increment without exploding cardinality
- `classify_error` buckets typical exceptions into the four allowed labels
"""
from __future__ import annotations

import asyncio
import logging
from io import StringIO
from uuid import uuid4

import httpx
import pytest
from prometheus_client import REGISTRY

from src.analyses.schemas import ErrorCode, SectionSlug
from src.jobs.orchestrator import TerminalError, TransientError
from src.monitoring import (
    bind_contextvars,
    clear_contextvars,
    get_logger,
)
from src.monitoring_metrics import (
    CACHE_HITS,
    CLOUD_TASKS_REDELIVERIES,
    SECTION_FAILURES,
    SINGLE_FLIGHT_LOCK_WAITS,
    classify_error,
)


@pytest.fixture
def captured_log() -> tuple[logging.Logger, StringIO]:
    """A logger whose output streams into a StringIO with our format + filters.

    The fixture re-imports the production filters so the test exercises the
    same `_ContextFilter` + `_SanitizeFilter` pair the real app uses.
    """
    from src.monitoring import (
        _DATE_FORMAT,
        _LOG_FORMAT,
        _ContextFilter,
        _SanitizeFilter,
    )

    logger = get_logger("test_observability_capture")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    sink = StringIO()
    handler = logging.StreamHandler(sink)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(_ContextFilter())
    handler.addFilter(_SanitizeFilter())
    logger.addHandler(handler)
    return logger, sink


class TestContextvarInjection:
    def test_log_record_picks_up_job_and_attempt_ids(
        self, captured_log: tuple[logging.Logger, StringIO]
    ) -> None:
        logger, sink = captured_log
        job_id = uuid4()
        attempt_id = uuid4()
        tokens = bind_contextvars(job_id=job_id, attempt_id=attempt_id)
        try:
            logger.info("hello world")
        finally:
            clear_contextvars(tokens)

        out = sink.getvalue()
        assert f"job_id={job_id}" in out
        assert f"attempt_id={attempt_id}" in out
        assert "slug=-" in out

    def test_section_slug_renders_enum_value(
        self, captured_log: tuple[logging.Logger, StringIO]
    ) -> None:
        logger, sink = captured_log
        tokens = bind_contextvars(slug=SectionSlug.FACTS_CLAIMS_DEDUP)
        try:
            logger.info("section step")
        finally:
            clear_contextvars(tokens)

        assert "slug=facts_claims__dedup" in sink.getvalue()

    def test_clear_contextvars_resets_to_default(
        self, captured_log: tuple[logging.Logger, StringIO]
    ) -> None:
        logger, sink = captured_log
        tokens = bind_contextvars(job_id="abc")
        clear_contextvars(tokens)
        logger.info("after clear")

        out = sink.getvalue()
        assert "job_id=-" in out

    def test_concurrent_coroutines_get_independent_context(
        self, captured_log: tuple[logging.Logger, StringIO]
    ) -> None:
        """Each coroutine must see its own contextvars, not bleed from a peer."""
        logger, sink = captured_log

        async def emit(slug_name: str) -> None:
            tokens = bind_contextvars(slug=slug_name)
            try:
                await asyncio.sleep(0)
                logger.info("from-%s", slug_name)
            finally:
                clear_contextvars(tokens)

        async def driver() -> None:
            await asyncio.gather(emit("alpha"), emit("beta"))

        asyncio.run(driver())
        out = sink.getvalue()
        assert "slug=alpha" in out
        assert "slug=beta" in out
        # No leak: a record tagged 'alpha' must not also carry 'beta'.
        for line in out.splitlines():
            if "from-alpha" in line:
                assert "slug=alpha" in line
            elif "from-beta" in line:
                assert "slug=beta" in line


class TestSanitizeFilterRedactsSignedUrls:
    def test_supabase_signed_url_token_is_redacted(
        self, captured_log: tuple[logging.Logger, StringIO]
    ) -> None:
        logger, sink = captured_log
        signed_url = (
            "https://abc.supabase.co/storage/v1/object/sign/scrapes/foo.html"
            "?token=eyJhbGciOiJIUzI1NiJ9.payload.SUPER_SECRET"
        )
        logger.info("scrape ready at %s", signed_url)

        out = sink.getvalue()
        assert "SUPER_SECRET" not in out
        assert "eyJhbGciOiJIUzI1NiJ9" not in out
        assert "<redacted>" in out

    def test_xamz_signature_is_redacted(
        self, captured_log: tuple[logging.Logger, StringIO]
    ) -> None:
        logger, sink = captured_log
        url = "https://s3.amazonaws.com/bucket/key?X-Amz-Signature=DEADBEEF1234"
        logger.warning("download from %s", url)

        out = sink.getvalue()
        assert "DEADBEEF1234" not in out
        assert "<redacted>" in out


class TestPrometheusCounters:
    def test_section_failures_increments_with_bounded_labels(self) -> None:
        labels = {"slug": "facts_claims__dedup", "error_type": "timeout"}
        before = REGISTRY.get_sample_value(
            "vibecheck_section_failures_total", labels=labels
        ) or 0.0
        SECTION_FAILURES.labels(**labels).inc()
        after = REGISTRY.get_sample_value(
            "vibecheck_section_failures_total", labels=labels
        )
        assert after == before + 1

    def test_cache_hits_increments_per_tier(self) -> None:
        labels = {"tier": "analysis"}
        before = REGISTRY.get_sample_value(
            "vibecheck_cache_hits_total", labels=labels
        ) or 0.0
        CACHE_HITS.labels(**labels).inc()
        after = REGISTRY.get_sample_value(
            "vibecheck_cache_hits_total", labels=labels
        )
        assert after == before + 1

    def test_cloud_tasks_redeliveries_is_unlabeled(self) -> None:
        before = REGISTRY.get_sample_value(
            "vibecheck_cloud_tasks_redeliveries_total"
        ) or 0.0
        CLOUD_TASKS_REDELIVERIES.inc()
        after = REGISTRY.get_sample_value(
            "vibecheck_cloud_tasks_redeliveries_total"
        )
        assert after == before + 1

    def test_single_flight_lock_waits_increments(self) -> None:
        before = REGISTRY.get_sample_value(
            "vibecheck_single_flight_lock_waits_total"
        ) or 0.0
        SINGLE_FLIGHT_LOCK_WAITS.inc()
        after = REGISTRY.get_sample_value(
            "vibecheck_single_flight_lock_waits_total"
        )
        assert after == before + 1


class TestClassifyError:
    def test_asyncio_timeout_buckets_to_timeout(self) -> None:
        assert classify_error(asyncio.TimeoutError()) == "timeout"  # noqa: UP041

    def test_builtin_timeout_buckets_to_timeout(self) -> None:
        assert classify_error(TimeoutError()) == "timeout"

    def test_httpx_timeout_buckets_to_timeout(self) -> None:
        assert classify_error(httpx.ConnectTimeout("slow")) == "timeout"

    def test_terminal_extraction_failure_buckets_to_extraction(self) -> None:
        exc = TerminalError(ErrorCode.EXTRACTION_FAILED, "html unparseable")
        assert classify_error(exc) == "extraction"

    def test_terminal_upstream_failure_buckets_to_upstream(self) -> None:
        exc = TerminalError(ErrorCode.UPSTREAM_ERROR, "firecrawl 503")
        assert classify_error(exc) == "upstream"

    def test_terminal_internal_default_buckets_to_internal(self) -> None:
        exc = TerminalError(ErrorCode.INTERNAL, "boom")
        assert classify_error(exc) == "internal"

    def test_transient_error_buckets_to_upstream(self) -> None:
        assert classify_error(TransientError("retry")) == "upstream"

    def test_httpx_http_error_buckets_to_upstream(self) -> None:
        exc = httpx.HTTPError("upstream 503")
        assert classify_error(exc) == "upstream"

    def test_value_error_buckets_to_internal(self) -> None:
        assert classify_error(ValueError("bad input")) == "internal"

    def test_generic_exception_buckets_to_internal(self) -> None:
        assert classify_error(Exception("generic")) == "internal"
