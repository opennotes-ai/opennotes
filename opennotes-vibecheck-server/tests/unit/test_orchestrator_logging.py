"""Tests for structured exception logging at UtteranceExtractionError catch sites.

Verifies that when UtteranceExtractionError is raised with a chained
pydantic ValidationError, the orchestrator logs a WARNING for
'vibecheck.extraction_failed' with exc_info populated before re-raising
TerminalError.  TASK-1526.01.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.analyses.schemas import ErrorCode
from src.jobs.orchestrator import TerminalError
from src.utterances.errors import UtteranceExtractionError


def _make_validation_error() -> ValidationError:
    """Build a real pydantic ValidationError with a recognisable field path."""
    from pydantic import BaseModel

    class _M(BaseModel):
        timestamp: int

    try:
        _M.model_validate({"timestamp": "not-an-int"})
    except ValidationError as exc:
        return exc
    raise AssertionError("unreachable")


def _make_utterance_extraction_error() -> UtteranceExtractionError:
    """Build an UtteranceExtractionError chained to a pydantic ValidationError."""
    ve = _make_validation_error()
    try:
        raise UtteranceExtractionError("parse failed") from ve
    except UtteranceExtractionError as exc:
        return exc


@pytest.mark.asyncio
async def test_first_pass_extraction_error_logs_warning_with_exc_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """UtteranceExtractionError on the first _scrape_and_extract call must log
    'vibecheck.extraction_failed' at WARNING with exc_info before raising
    TerminalError(EXTRACTION_FAILED).
    """
    import src.jobs.orchestrator as orch_mod

    extraction_exc = _make_utterance_extraction_error()
    job_id = uuid4()
    task_attempt = uuid4()
    url = "https://example.com/article"

    fake_pool = MagicMock()
    fake_pool.acquire = MagicMock(return_value=AsyncMock())
    fake_settings = MagicMock()

    async def _raise_extraction(*args: object, **kwargs: object) -> None:
        raise extraction_exc

    with (
        patch.object(orch_mod, "_build_scrape_cache", return_value=MagicMock()),
        patch.object(orch_mod, "_build_firecrawl_client", return_value=MagicMock()),
        patch.object(orch_mod, "_build_firecrawl_tier1_client", return_value=MagicMock()),
        patch.object(orch_mod, "extract_utterances", side_effect=_raise_extraction),
        patch.object(orch_mod, "_scrape_step", new=AsyncMock(return_value=MagicMock())),
        patch.object(orch_mod, "_revalidate_final_url", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger="src.jobs.orchestrator"),
        pytest.raises(TerminalError) as exc_info_ctx,
    ):
        await orch_mod._run_pipeline(
            fake_pool,
            job_id,
            task_attempt,
            url,
            fake_settings,
        )

    terminal_err = exc_info_ctx.value
    assert terminal_err.error_code == ErrorCode.EXTRACTION_FAILED

    matching = [
        r for r in caplog.records
        if r.getMessage() == "vibecheck.extraction_failed"
        and r.levelno == logging.WARNING
    ]
    assert matching, (
        "Expected a WARNING log record with message 'vibecheck.extraction_failed' "
        f"but got: {[r.getMessage() for r in caplog.records]}"
    )
    record = matching[0]
    assert record.exc_info is not None, (
        "Expected exc_info to be set on 'vibecheck.extraction_failed' log record"
    )
    _, exc_val, _ = record.exc_info
    assert isinstance(exc_val, UtteranceExtractionError), (
        f"Expected exc_info exception to be UtteranceExtractionError, got {type(exc_val)}"
    )
    assert isinstance(exc_val.__cause__, ValidationError), (
        "Expected UtteranceExtractionError.__cause__ to be a pydantic ValidationError"
    )


@pytest.mark.asyncio
async def test_second_pass_extraction_error_logs_warning_with_exc_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """UtteranceExtractionError on the second _scrape_and_extract call (after
    ZeroUtterancesError escalation) must also log 'vibecheck.extraction_failed'
    at WARNING with exc_info before raising TerminalError(EXTRACTION_FAILED).
    """
    import src.jobs.orchestrator as orch_mod
    from src.utterances.errors import ZeroUtterancesError

    extraction_exc = _make_utterance_extraction_error()
    job_id = uuid4()
    task_attempt = uuid4()
    url = "https://example.com/article"

    fake_pool = MagicMock()
    fake_settings = MagicMock()

    call_count = 0

    async def _first_zero_then_extraction(*args: object, **kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ZeroUtterancesError("first pass empty")
        raise extraction_exc

    with (
        patch.object(orch_mod, "_build_scrape_cache", return_value=MagicMock()),
        patch.object(orch_mod, "_build_firecrawl_client", return_value=MagicMock()),
        patch.object(orch_mod, "_build_firecrawl_tier1_client", return_value=MagicMock()),
        patch.object(orch_mod, "extract_utterances", side_effect=_first_zero_then_extraction),
        patch.object(orch_mod, "_scrape_step", new=AsyncMock(return_value=MagicMock())),
        patch.object(orch_mod, "_revalidate_final_url", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger="src.jobs.orchestrator"),
        pytest.raises(TerminalError) as exc_info_ctx,
    ):
        await orch_mod._run_pipeline(
            fake_pool,
            job_id,
            task_attempt,
            url,
            fake_settings,
        )

    terminal_err = exc_info_ctx.value
    assert terminal_err.error_code == ErrorCode.EXTRACTION_FAILED

    matching = [
        r for r in caplog.records
        if r.getMessage() == "vibecheck.extraction_failed"
        and r.levelno == logging.WARNING
    ]
    assert matching, (
        "Expected a WARNING log record with message 'vibecheck.extraction_failed' "
        f"but got: {[r.getMessage() for r in caplog.records]}"
    )
    record = matching[0]
    assert record.exc_info is not None, (
        "Expected exc_info to be set on 'vibecheck.extraction_failed' log record"
    )
