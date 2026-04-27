"""Exception types and classifiers for the utterance-extraction call site.

The orchestrator catches these and translates to TransientError /
TerminalError per the Cloud Tasks retry contract:

- A `TransientExtractionError` returned by `classify_pydantic_ai_error` /
  `classify_firecrawl_error` becomes a TransientError(UPSTREAM_ERROR), which
  the run_job arm translates into HTTP 503 so Cloud Tasks redelivers the
  task. The in-row `extract_transient_attempts` counter (TASK-1474.23.03.01)
  acts as the backstop: once it exceeds the configured cap, the next
  transient surface is converted to a TerminalError(UPSTREAM_ERROR) so the
  job terminates instead of silently exhausting Cloud Tasks max_attempts.

- A None return from a classifier means the caller should treat the
  exception as terminal `EXTRACTION_FAILED` (parse failure, schema
  validation, no utterances) and fail the job without retry.

The classifiers are pure (no I/O, no logfire). Logfire span attributes
based on the `TransientExtractionError` payload are set at the call site
in the orchestrator (TASK-1474.23.03.04 + .05).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Final

import httpx
from pydantic_ai.exceptions import ModelHTTPError

from src.firecrawl_client import FirecrawlError, _RetryableHTTPStatusError

# Vertex AI / Gemini retriable status codes (RESOURCE_EXHAUSTED 429,
# INTERNAL 500, UNAVAILABLE 503, DEADLINE_EXCEEDED 504). Google's retry
# guidance lists 500 alongside 503/504 as transient — kept symmetric with
# the Firecrawl set so a Vertex 500 doesn't silently terminate the job.
_VERTEX_RETRIABLE_STATUSES: Final[frozenset[int]] = frozenset(
    {429, 500, 503, 504}
)

# Firecrawl retriable HTTP statuses (rate-limit + 5xx).
_FIRECRAWL_RETRIABLE_STATUSES: Final[frozenset[int]] = frozenset(
    {429, 500, 502, 503, 504}
)


class UtteranceExtractionError(Exception):
    """Terminal failure during extract_utterances (parse failure, no
    utterances, output validation). Orchestrator translates to
    TerminalError(EXTRACTION_FAILED).
    """


@dataclass
class TransientExtractionError(Exception):
    """Transient upstream failure during extract_utterances.

    Orchestrator translates to TransientError(UPSTREAM_ERROR) so Cloud
    Tasks redelivers, until the in-row backstop counter exhausts.

    Attributes are exposed for Logfire span attributes (upstream_provider,
    upstream_status_code, upstream_status, model_name).
    """

    provider: str  # 'vertex' | 'firecrawl'
    status_code: int | None = None
    status: str | None = None
    model_name: str | None = None
    fallback_message: str = "transient upstream error"

    def __post_init__(self) -> None:
        super().__init__(self.fallback_message)


def _walk_cause_chain(exc: BaseException) -> list[BaseException]:
    """Return [exc, exc.__cause__, exc.__context__, ...] in BFS order,
    deduplicated by identity, capped at 8 to avoid pathological cycles.

    Per PEP 3134, when both `__cause__` (explicit `raise X from Y`) and
    `__context__` (implicit prior raise inside an except) are set, the
    explicit cause is the author's intent and must win. We enqueue
    `__cause__` before `__context__` and use a FIFO queue so the cause
    branch is fully visited before the context branch at the same depth.
    """
    seen: list[BaseException] = []
    seen_ids: set[int] = set()
    queue: deque[BaseException] = deque([exc])
    while queue and len(seen) < 8:
        cur = queue.popleft()
        if id(cur) in seen_ids:
            continue
        seen_ids.add(id(cur))
        seen.append(cur)
        if cur.__cause__ is not None:
            queue.append(cur.__cause__)
        if cur.__context__ is not None and not cur.__suppress_context__:
            queue.append(cur.__context__)
    return seen


def _find_inner_model_http_error(exc: BaseException) -> ModelHTTPError | None:
    """Walk the FULL cause/context chain and prefer a retriable
    ModelHTTPError over a non-retriable one.

    Both direct `raise ModelHTTPError(...)` AND
    `UnexpectedModelBehavior(__cause__=ModelHTTPError(...))` must surface
    the inner status_code so the classifier returns transient for
    429/500/503/504. If a non-retriable ModelHTTPError appears earlier
    in the walked chain and a retriable one appears later, the retriable
    one wins — otherwise the classifier would terminate jobs that should
    redeliver. Falls back to the first ModelHTTPError if none retriable.
    """
    first: ModelHTTPError | None = None
    for inner in _walk_cause_chain(exc):
        if isinstance(inner, ModelHTTPError):
            if inner.status_code in _VERTEX_RETRIABLE_STATUSES:
                return inner
            if first is None:
                first = inner
    return first


def _vertex_status_name(status_code: int) -> str:
    return {
        429: "RESOURCE_EXHAUSTED",
        500: "INTERNAL",
        503: "UNAVAILABLE",
        504: "DEADLINE_EXCEEDED",
    }.get(status_code, f"HTTP_{status_code}")


def classify_pydantic_ai_error(
    exc: BaseException, *, model_name: str | None = None
) -> TransientExtractionError | None:
    """Classify a pydantic-ai exception.

    Returns `TransientExtractionError` if the inner HTTP status / network
    error is retriable; `None` otherwise (caller should treat as terminal
    EXTRACTION_FAILED).

    Retriable cases:
    - Direct ModelHTTPError(429|503|504) — Vertex DEADLINE_EXCEEDED,
      UNAVAILABLE, RESOURCE_EXHAUSTED
    - UnexpectedModelBehavior wrapping ModelHTTPError with retriable status
    - asyncio.TimeoutError / httpx.TimeoutException / httpx.TransportError
      in the cause chain
    """
    inner_http = _find_inner_model_http_error(exc)
    if (
        inner_http is not None
        and inner_http.status_code in _VERTEX_RETRIABLE_STATUSES
    ):
        return TransientExtractionError(
            provider="vertex",
            status_code=inner_http.status_code,
            status=_vertex_status_name(inner_http.status_code),
            model_name=model_name,
            fallback_message=f"Vertex {inner_http.status_code}: {inner_http}",
        )

    for inner in _walk_cause_chain(exc):
        if isinstance(inner, TimeoutError | httpx.TimeoutException):
            return TransientExtractionError(
                provider="vertex",
                status=type(inner).__name__,
                model_name=model_name,
                fallback_message=f"upstream timeout: {inner}",
            )
        if isinstance(inner, httpx.TransportError):
            return TransientExtractionError(
                provider="vertex",
                status=type(inner).__name__,
                model_name=model_name,
                fallback_message=f"upstream transport error: {inner}",
            )

    return None


def classify_firecrawl_error(
    exc: BaseException,
) -> TransientExtractionError | None:
    """Classify a Firecrawl client exception.

    Returns `TransientExtractionError` if the status / network error is
    retriable; `None` otherwise.

    Retriable cases:
    - FirecrawlError with status_code in {429, 500, 502, 503, 504}
    - _RetryableHTTPStatusError (private internal type) — already escaped
      tenacity
    - httpx.TransportError / httpx.TimeoutException in the cause chain
    """
    for inner in _walk_cause_chain(exc):
        if isinstance(inner, FirecrawlError):
            sc = getattr(inner, "status_code", None)
            if sc in _FIRECRAWL_RETRIABLE_STATUSES:
                return TransientExtractionError(
                    provider="firecrawl",
                    status_code=sc,
                    status=f"HTTP_{sc}",
                    fallback_message=f"Firecrawl {sc}: {inner}",
                )
        if isinstance(inner, _RetryableHTTPStatusError):
            return TransientExtractionError(
                provider="firecrawl",
                status=type(inner).__name__,
                fallback_message=f"Firecrawl retriable: {inner}",
            )
        if isinstance(inner, httpx.TimeoutException | httpx.TransportError):
            return TransientExtractionError(
                provider="firecrawl",
                status=type(inner).__name__,
                fallback_message=f"Firecrawl transport error: {inner}",
            )
    return None
