"""Tests for src/utterances/errors.py classifiers (TASK-1474.23.03.02).

These pin the orchestrator's translation contract: a transient pydantic-ai
or Firecrawl failure (Vertex DEADLINE_EXCEEDED, UNAVAILABLE,
RESOURCE_EXHAUSTED, network timeout, transport drop) must surface as
TransientExtractionError so the orchestrator can convert it to a Cloud
Tasks redelivery; everything else is None and the caller treats it as a
terminal EXTRACTION_FAILED. The classifiers are pure functions — no I/O,
no logfire — so we can hammer them with synthetic exceptions without a
container.
"""
from __future__ import annotations

import httpx
import pytest
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior

from src.utterances.errors import (
    TransientExtractionError,
    classify_firecrawl_error,
    classify_pydantic_ai_error,
)


@pytest.mark.parametrize("status_code", [429, 503, 504])
def test_classify_direct_model_http_error_returns_transient(status_code: int) -> None:
    exc = ModelHTTPError(status_code=status_code, model_name="gemini-2.5-pro", body=None)
    result = classify_pydantic_ai_error(exc, model_name="gemini-2.5-pro")
    assert isinstance(result, TransientExtractionError)
    assert result.provider == "vertex"
    assert result.status_code == status_code
    assert result.model_name == "gemini-2.5-pro"


def test_classify_unexpected_model_behavior_unwraps_inner_http_error() -> None:
    inner = ModelHTTPError(status_code=504, model_name="gemini-2.5-pro", body=None)
    outer = UnexpectedModelBehavior("tool retry exhausted")
    outer.__cause__ = inner
    result = classify_pydantic_ai_error(outer, model_name="gemini-2.5-pro")
    assert isinstance(result, TransientExtractionError)
    assert result.status_code == 504
    assert result.status == "DEADLINE_EXCEEDED"


def test_classify_non_retriable_status_returns_none() -> None:
    exc = ModelHTTPError(status_code=400, model_name="gemini-2.5-pro", body=None)
    assert classify_pydantic_ai_error(exc) is None


def test_classify_asyncio_timeout_returns_transient() -> None:
    timeout = TimeoutError("upstream timeout")
    result = classify_pydantic_ai_error(timeout)
    assert isinstance(result, TransientExtractionError)
    assert result.provider == "vertex"


def test_classify_httpx_timeout_returns_transient() -> None:
    exc = httpx.ReadTimeout("read timeout")
    result = classify_pydantic_ai_error(exc)
    assert isinstance(result, TransientExtractionError)


def test_classify_httpx_transport_error_returns_transient() -> None:
    exc = httpx.ConnectError("connection refused")
    result = classify_pydantic_ai_error(exc)
    assert isinstance(result, TransientExtractionError)


def test_classify_firecrawl_503_returns_transient() -> None:
    from src.firecrawl_client import FirecrawlError

    exc = FirecrawlError("upstream unavailable", status_code=503)
    result = classify_firecrawl_error(exc)
    assert isinstance(result, TransientExtractionError)
    assert result.provider == "firecrawl"
    assert result.status_code == 503


def test_classify_firecrawl_404_returns_none() -> None:
    from src.firecrawl_client import FirecrawlError

    exc = FirecrawlError("not found", status_code=404)
    assert classify_firecrawl_error(exc) is None


def test_classify_firecrawl_httpx_transport_returns_transient() -> None:
    exc = httpx.ConnectError("connection refused")
    result = classify_firecrawl_error(exc)
    assert isinstance(result, TransientExtractionError)


def test_classify_unrelated_exception_returns_none() -> None:
    exc = ValueError("totally unrelated")
    assert classify_pydantic_ai_error(exc) is None
    assert classify_firecrawl_error(exc) is None
