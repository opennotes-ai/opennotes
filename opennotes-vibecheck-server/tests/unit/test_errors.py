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


@pytest.mark.parametrize(
    "status_code",
    [429, 500, 503, 504],
    ids=["429-rate-limit", "500-internal", "503-unavailable", "504-deadline"],
)
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


@pytest.mark.parametrize(
    "status_code",
    [429, 500, 502, 503, 504],
    ids=["429-rate-limit", "500-internal", "502-bad-gateway", "503-unavailable", "504-deadline"],
)
def test_classify_firecrawl_retriable_status_returns_transient(status_code: int) -> None:
    from src.firecrawl_client import FirecrawlError

    exc = FirecrawlError("upstream unavailable", status_code=status_code)
    result = classify_firecrawl_error(exc)
    assert isinstance(result, TransientExtractionError)
    assert result.provider == "firecrawl"
    assert result.status_code == status_code


def test_classify_firecrawl_retryable_http_status_error_returns_transient() -> None:
    """The private _RetryableHTTPStatusError that escapes tenacity must
    classify as transient — pins the dead-by-coverage branch in errors.py.
    """
    from src.firecrawl_client import _RetryableHTTPStatusError

    exc = _RetryableHTTPStatusError(503, "upstream temporarily unavailable")
    result = classify_firecrawl_error(exc)
    assert isinstance(result, TransientExtractionError)
    assert result.provider == "firecrawl"


def test_classify_firecrawl_httpx_timeout_returns_transient() -> None:
    """Mirrors the Vertex-arm httpx.ReadTimeout test for the Firecrawl arm."""
    exc = httpx.ReadTimeout("upstream read timeout")
    result = classify_firecrawl_error(exc)
    assert isinstance(result, TransientExtractionError)
    assert result.provider == "firecrawl"


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


def test_walk_prefers_cause_over_context_per_pep_3134() -> None:
    """PEP 3134: when both __cause__ and __context__ are set, __cause__
    is the explicit author intent and must be visited before __context__.

    Pin this with a chain where the *cause* branch holds a retriable
    ModelHTTPError(504) and the *context* branch holds a non-retriable
    ModelHTTPError(400). With the LIFO bug, the context (400) is popped
    first and `_find_inner_model_http_error` returned terminal. After
    the fix, the cause (504) wins — classifier returns transient.
    """
    inner_retriable = ModelHTTPError(status_code=504, model_name="gemini-2.5-pro", body=None)
    inner_non_retriable_context = ModelHTTPError(
        status_code=400, model_name="gemini-2.5-pro", body=None
    )
    outer = UnexpectedModelBehavior("tool retry exhausted")
    outer.__cause__ = inner_retriable
    outer.__context__ = inner_non_retriable_context
    outer.__suppress_context__ = False

    result = classify_pydantic_ai_error(outer, model_name="gemini-2.5-pro")
    assert isinstance(result, TransientExtractionError)
    assert result.status_code == 504
    assert result.status == "DEADLINE_EXCEEDED"


def test_classify_picks_retriable_after_non_retriable_in_chain() -> None:
    """If a non-retriable ModelHTTPError(400) appears earlier in the
    chain and a retriable ModelHTTPError(504) appears deeper, the
    classifier must pick the retriable one — not return terminal.
    """
    deeper_retriable = ModelHTTPError(status_code=504, model_name="gemini-2.5-pro", body=None)
    earlier_non_retriable = ModelHTTPError(status_code=400, model_name="gemini-2.5-pro", body=None)
    earlier_non_retriable.__cause__ = deeper_retriable
    outer = UnexpectedModelBehavior("tool retry exhausted")
    outer.__cause__ = earlier_non_retriable

    result = classify_pydantic_ai_error(outer, model_name="gemini-2.5-pro")
    assert isinstance(result, TransientExtractionError)
    assert result.status_code == 504

    deeper_non_retriable = ModelHTTPError(status_code=401, model_name="gemini-2.5-pro", body=None)
    earlier_non_retriable_2 = ModelHTTPError(status_code=400, model_name="gemini-2.5-pro", body=None)
    earlier_non_retriable_2.__cause__ = deeper_non_retriable
    outer2 = UnexpectedModelBehavior("tool retry exhausted")
    outer2.__cause__ = earlier_non_retriable_2

    assert classify_pydantic_ai_error(outer2) is None


def test_cause_non_retriable_anchors_over_context_timeout() -> None:
    """PEP 3134 BFS bug: outer's __cause__ is non-retriable
    ModelHTTPError(400) and outer's __context__ is TimeoutError. The
    explicit cause must anchor the classifier decision; the implicit
    timeout in __context__ must not flip the result to transient.
    """
    non_retriable_cause = ModelHTTPError(
        status_code=400, model_name="gemini-2.5-pro", body=None
    )
    context_timeout = TimeoutError("upstream context timeout")
    outer = UnexpectedModelBehavior("tool retry exhausted")
    outer.__cause__ = non_retriable_cause
    outer.__context__ = context_timeout
    outer.__suppress_context__ = False

    assert classify_pydantic_ai_error(outer, model_name="gemini-2.5-pro") is None


def test_cause_chain_retriable_deeper_wins_over_context_retriable() -> None:
    """Cause-chain depth wins: outer.__cause__ is non-retriable 400 whose
    own __cause__ is retriable 504; outer.__context__ is a retriable
    TimeoutError. The cause-chain decision must anchor (504 transient
    with status_code populated) — not the context timeout (which would
    leave status_code unset).
    """
    deeper_retriable = ModelHTTPError(
        status_code=504, model_name="gemini-2.5-pro", body=None
    )
    cause_non_retriable = ModelHTTPError(
        status_code=400, model_name="gemini-2.5-pro", body=None
    )
    cause_non_retriable.__cause__ = deeper_retriable
    context_timeout = TimeoutError("retriable context timeout")
    outer = UnexpectedModelBehavior("tool retry exhausted")
    outer.__cause__ = cause_non_retriable
    outer.__context__ = context_timeout
    outer.__suppress_context__ = False

    result = classify_pydantic_ai_error(outer, model_name="gemini-2.5-pro")
    assert isinstance(result, TransientExtractionError)
    assert result.status_code == 504
    assert result.status == "DEADLINE_EXCEEDED"


def test_walk_cause_chain_terminates_on_cycle() -> None:
    """Synthetic __cause__ cycle must not hang the walker."""
    from src.utterances.errors import _walk_cause_chain

    a = Exception("a")
    b = Exception("b")
    a.__cause__ = b
    b.__cause__ = a

    walked = _walk_cause_chain(a)
    assert len(walked) <= 8
    assert any(x is a for x in walked)
    assert any(x is b for x in walked)

    assert classify_pydantic_ai_error(a) is None
