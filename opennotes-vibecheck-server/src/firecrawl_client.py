"""Async wrapper over the Firecrawl v2 HTTP API.

Endpoints exposed:
- ``extract()``  -> /v2/extract  (poll-and-wait async job)
- ``scrape()``   -> /v2/scrape   (single-shot HTML/markdown/screenshot)
- ``interact()`` -> /v2/scrape with ``actions`` field (scrape + scripted browser actions)

Why ``interact()`` posts to /v2/scrape: Firecrawl v2 has no ``/v2/interact``
endpoint — live calls return ``404 Cannot POST /v2/interact``. Per the
official v2 docs, browser actions are part of /v2/scrape via the ``actions``
array. The public method name is preserved so the orchestrator's tier wiring
keeps calling ``client.interact(...)``, but the request goes to /v2/scrape.

Retry/attempt model (TASK-1488 ladder integration)
--------------------------------------------------
``FirecrawlClient(max_attempts=N)`` controls the retry budget shared by all
three endpoints. The vibecheck extractor uses two distinct call patterns:

- **Tier 1 (fail-fast probe):** construct ``FirecrawlClient(max_attempts=1)``.
  A single HTTP call is made; transient 5xx surfaces immediately as a
  ``FirecrawlError`` rather than burning ~7s on the default exponential
  backoff. Use this when the orchestrator plans to escalate to a fallback
  tier (scrape, then interact) on any failure — retries at this layer
  delay that escalation without adding value.
- **Tier 2 (resilient default):** keep the default ``max_attempts=3``. This
  is the right setting for callers that have no fallback path and need the
  built-in 1s/2s/4s backoff to ride out transient Firecrawl-side blips.

Refusal detection
-----------------
Firecrawl signals "we won't fetch this URL" through a small set of stable
phrases in either the JSON envelope (``{"success": false, "error": "..."}``)
or the body of a 4xx response. Those refusals are surfaced as the typed
``FirecrawlBlocked`` exception (a subclass of ``FirecrawlError``) so callers
can branch — e.g., terminate the ladder early without retrying — instead of
parsing error strings at the call site. The marker list is deliberately
conservative; see ``_REFUSAL_MARKERS`` for the canonical phrases.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

FIRECRAWL_API_BASE = "https://api.firecrawl.dev"
DEFAULT_TIMEOUT_SECONDS = 120.0
_RETRY_STATUS = {429, 500, 502, 503, 504}

_DEFAULT_INTERACT_FORMATS: tuple[str, ...] = ("markdown", "html", "screenshot@fullPage")

_REFUSAL_MARKERS: tuple[str, ...] = (
    "no longer supported",
    "firecrawl does not support",
    "this website is blocked",
    # TASK-1488.09: real Firecrawl refusal envelope captured in 1488.07 live
    # verification: `{"success":false,"error":"We apologize for the
    # inconvenience but we do not support this site..."}`. Without this
    # marker LinkedIn/Reddit refusals were classified as TransientError,
    # triggering infinite Cloud Tasks retries on a stable refusal.
    "we do not support this site",
)


def _looks_like_refusal(text: str | None) -> bool:
    """Return True iff `text` contains a documented refusal phrase.

    Markers are matched case-insensitively against the raw string. The list
    is intentionally short — false positives would terminate legitimate
    content paths in the orchestrator. Extend cautiously, ideally after
    capturing a real refusal body during 1488.07.
    """
    if not text:
        return False
    haystack = text.lower()
    return any(marker in haystack for marker in _REFUSAL_MARKERS)


_FIRECRAWL_UNSUPPORTED_KEYS = frozenset(
    {
        # Firecrawl's /v2/extract rejects schemas that reference $defs/$ref
        # (it doesn't resolve them) and rejects `format: date-time` and other
        # format hints. Drop all of these — we reparse datetimes in Pydantic
        # post-fetch.
        "$defs",
        "definitions",
        "format",
    }
)


def _inline_defs(schema: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Pydantic-generated JSON schema for Firecrawl's /v2/extract.

    - Inline every $ref into the target subschema (drop $defs).
    - Strip `format` keys (Firecrawl rejects format: date-time etc.).
    """
    defs = schema.get("$defs") or schema.get("definitions") or {}

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith(("#/$defs/", "#/definitions/")):
                key = ref.rsplit("/", 1)[-1]
                target = defs.get(key)
                if isinstance(target, dict):
                    return walk(dict(target))
                return {}
            return {k: walk(v) for k, v in node.items() if k not in _FIRECRAWL_UNSUPPORTED_KEYS}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def _format_to_object(fmt: str) -> dict[str, Any]:
    """Translate a legacy string format into Firecrawl v2's object form.

    Firecrawl's current /v2/scrape validator rejects bare-string formats
    with `invalid_union` on path ["type"] — each format must be an object
    with a `type` field. The `screenshot@fullPage` shorthand is how our
    callers historically requested a full-page screenshot; map it to the
    documented `{"type": "screenshot", "fullPage": true}` shape.
    """
    if fmt == "screenshot@fullPage":
        return {"type": "screenshot", "fullPage": True}
    return {"type": fmt}


class ScrapeMetadata(BaseModel):
    # `validation_alias=AliasChoices(snake_case, camelCase)` lets Pydantic
    # accept either shape on the way *in* (wire JSON uses `sourceURL`;
    # Python call sites use `source_url`) while keeping the Python field
    # name as the primary parameter so basedpyright doesn't treat the
    # alias as a required-by-keyword argument. `default=None` is explicit
    # so every field is optional — required for `ScrapeMetadata(...)` to
    # type-check with any subset of kwargs.
    title: str | None = Field(default=None)
    description: str | None = Field(default=None)
    language: str | None = Field(default=None)
    source_url: str | None = Field(
        default=None, validation_alias=AliasChoices("source_url", "sourceURL")
    )
    status_code: int | None = Field(
        default=None, validation_alias=AliasChoices("status_code", "statusCode")
    )
    error: str | None = Field(default=None)
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @field_validator("language", mode="before")
    @classmethod
    def _coerce_language_list(cls, value: Any) -> Any:
        """Accept ``language`` as either ``str`` or ``list[str]``.

        TASK-1488.10: live verification (1488.07) found that some pages —
        e.g., ``blog.cloudflare.com`` — return ``metadata.language=
        ["en-us", "en"]``. The previous ``str | None`` annotation rejected
        this with a pydantic validation error, which the orchestrator
        caught as ``FirecrawlError`` -> ``TransientError`` -> infinite
        Cloud Tasks retry on a 200-OK page. We don't use ``language`` for
        anything semantically meaningful right now, so coerce list -> first
        non-empty string and keep the field annotated as ``str | None`` for
        downstream simplicity.
        """
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item:
                    return item
            return None
        return value


class ScrapeResult(BaseModel):
    # See ScrapeMetadata comment — same rationale for `validation_alias`.
    markdown: str | None = Field(default=None)
    html: str | None = Field(default=None)
    raw_html: str | None = Field(
        default=None, validation_alias=AliasChoices("raw_html", "rawHtml")
    )
    screenshot: str | None = Field(default=None)
    links: list[str] | None = Field(default=None)
    metadata: ScrapeMetadata | None = Field(default=None)
    warning: str | None = Field(default=None)
    model_config = ConfigDict(populate_by_name=True)


class FirecrawlError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FirecrawlBlocked(FirecrawlError):  # noqa: N818 — named for the *condition* (refusal), not as a generic error; subclass of *Error already conveys exception-ness.
    """Firecrawl refused this URL (domain blocklist, ToS-flagged site,
    anti-bot wall).

    Subclass of :class:`FirecrawlError` so existing ``except FirecrawlError``
    blocks still catch it. Specific call sites can ``except FirecrawlBlocked``
    first to short-circuit retry/fallback logic — e.g., the Tier 1 probe in
    the vibecheck extractor immediately escalates to the next tier on
    refusal rather than retrying.
    """


class _RetryableHTTPStatusError(Exception):
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"firecrawl returned retryable status {status_code}: {body[:200]}")
        self.status_code = status_code
        self.body = body


class FirecrawlClient:
    """Thin async wrapper over the Firecrawl v2 HTTP API.

    Used by the utterance extractor (/v2/extract) and by the screenshot pipeline
    (/v2/scrape). Retries 429/5xx with exponential backoff (1s -> 2s -> 4s).
    """

    def __init__(
        self,
        api_key: str,
        *,
        api_base: str = FIRECRAWL_API_BASE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("FirecrawlClient requires a non-empty api_key")
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout
        self._max_attempts = max_attempts

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _retrying(self) -> AsyncRetrying:
        return AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type((_RetryableHTTPStatusError, httpx.TransportError)),
            reraise=True,
        )

    async def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._api_base}{path}"

        async def _send() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, headers=self._headers, json=body)
            if response.status_code in _RETRY_STATUS:
                raise _RetryableHTTPStatusError(response.status_code, response.text)
            if response.status_code >= 400:
                # 4xx with a documented refusal phrase in the body: surface
                # as FirecrawlBlocked so callers don't retry a refusal and
                # can fast-escalate to the next ladder tier.
                if _looks_like_refusal(response.text):
                    raise FirecrawlBlocked(
                        f"firecrawl {path} refused: {response.status_code} {response.text[:200]}",
                        status_code=response.status_code,
                    )
                raise FirecrawlError(
                    f"firecrawl {path} failed: {response.status_code} {response.text[:200]}",
                    status_code=response.status_code,
                )
            return response.json()

        async for attempt in self._retrying():
            with attempt:
                return await _send()
        raise FirecrawlError(f"firecrawl {path} exhausted retries")

    @staticmethod
    def _raise_for_envelope_failure(envelope: dict[str, Any], path: str) -> None:
        """Inspect a `{success: false, error: ...}` envelope and raise.

        Raises :class:`FirecrawlBlocked` when the error string matches a
        documented refusal marker; otherwise raises the generic
        :class:`FirecrawlError`. No-op when the envelope reports success.
        """
        if envelope.get("success") is not False:
            return
        error_text = str(envelope.get("error", "unknown"))
        if _looks_like_refusal(error_text):
            raise FirecrawlBlocked(f"firecrawl {path} refused: {error_text}")
        raise FirecrawlError(f"firecrawl {path} reported failure: {error_text}")

    async def extract(
        self,
        url: str,
        schema: type[BaseModel],
        *,
        poll_interval: float = 2.0,
        poll_timeout: float = 240.0,
    ) -> BaseModel:
        """Call Firecrawl /v2/extract and poll until the job completes.

        /v2/extract is async: the initial POST returns {success, id} immediately,
        then you GET /v2/extract/{id} repeatedly until status=completed and
        `data` is populated. Previous code assumed sync response and crashed on
        the empty first envelope.
        """
        body = {
            "urls": [url],
            "schema": _inline_defs(schema.model_json_schema()),
        }
        envelope = await self._post_json("/v2/extract", body)
        self._raise_for_envelope_failure(envelope, "/v2/extract")
        data = envelope.get("data")
        if data is None:
            job_id = envelope.get("id")
            if not job_id:
                raise FirecrawlError("firecrawl /v2/extract returned no job id and no data")
            data = await self._poll_extract(job_id, poll_interval=poll_interval, poll_timeout=poll_timeout)
        return schema.model_validate(data)

    async def _poll_extract(
        self, job_id: str, *, poll_interval: float, poll_timeout: float
    ) -> dict[str, Any]:
        """Poll GET /v2/extract/{id} until status=completed."""
        deadline = asyncio.get_event_loop().time() + poll_timeout
        url = f"{self._api_base}/v2/extract/{job_id}"
        while True:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=self._headers)
            if response.status_code >= 400:
                raise FirecrawlError(
                    f"firecrawl /v2/extract/{job_id} status poll failed: {response.status_code} {response.text[:200]}",
                    status_code=response.status_code,
                )
            envelope = response.json()
            status = envelope.get("status")
            if status == "completed":
                data = envelope.get("data")
                if data is None:
                    raise FirecrawlError(f"firecrawl /v2/extract/{job_id} completed with no data")
                return data
            if status in ("failed", "cancelled"):
                raise FirecrawlError(
                    f"firecrawl /v2/extract/{job_id} ended with status={status}: {envelope.get('error', '')}"
                )
            if asyncio.get_event_loop().time() > deadline:
                raise FirecrawlError(f"firecrawl /v2/extract/{job_id} polling timed out after {poll_timeout}s")
            await asyncio.sleep(poll_interval)

    async def scrape(
        self,
        url: str,
        formats: list[str],
        *,
        only_main_content: bool = False,
    ) -> ScrapeResult:
        """Call Firecrawl /v2/scrape and return a typed `ScrapeResult`.

        `formats` accepts values like ["markdown", "screenshot", "screenshot@fullPage"].
        `only_main_content=True` strips nav/footer/aside from the markdown,
        which gives much cleaner content for downstream parsing.

        Fields on the returned `ScrapeResult` are all optional: only the
        formats you requested are populated (Firecrawl omits the rest).
        """
        body: dict[str, Any] = {
            "url": url,
            "formats": [_format_to_object(fmt) for fmt in formats],
        }
        if only_main_content:
            body["onlyMainContent"] = True
        envelope = await self._post_json("/v2/scrape", body)
        self._raise_for_envelope_failure(envelope, "/v2/scrape")
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise FirecrawlError("firecrawl /v2/scrape returned no data object")
        return ScrapeResult.model_validate(data)

    async def interact(
        self,
        url: str,
        actions: list[dict[str, Any]],
        *,
        formats: list[str] | None = None,
        only_main_content: bool = False,
    ) -> ScrapeResult:
        """Call Firecrawl /v2/scrape with a scripted ``actions`` list and
        return a typed `ScrapeResult`.

        TASK-1488.08: Firecrawl v2 has no ``/v2/interact`` endpoint —
        live calls return ``404 Cannot POST /v2/interact``. Per the
        official v2 docs (https://docs.firecrawl.dev), browser actions are
        run by /v2/scrape via the ``actions`` array. This method routes
        through /v2/scrape under the hood while preserving its own name so
        the vibecheck orchestrator's Tier 2 wiring (``client.interact(url,
        actions=_TIER2_DEFAULT_ACTIONS)``) doesn't need to change.

        Used as the Tier 2 fallback in the vibecheck extractor ladder for
        sites that gate content behind consent banners, anti-bot walls, or
        login flows. Callers pass a list of ``actions`` (clicks, scrolls,
        waits, form fills) that run before content is captured.

        ``actions`` follows Firecrawl's documented action schema (each item
        is a dict with a ``type`` and type-specific keys); we pass them
        through verbatim so the orchestrator can build call-site-specific
        action lists without this client tracking the schema.

        ``formats`` defaults to ``markdown + html + screenshot@fullPage`` so
        callers get the same payload they'd get from ``scrape()``; pass
        explicitly to narrow it.

        Refusal detection and the constructor's retry budget apply to this
        call identically to ``scrape()``.
        """
        chosen_formats = list(formats) if formats is not None else list(_DEFAULT_INTERACT_FORMATS)
        body: dict[str, Any] = {
            "url": url,
            "actions": actions,
            "formats": [_format_to_object(fmt) for fmt in chosen_formats],
        }
        if only_main_content:
            body["onlyMainContent"] = True
        envelope = await self._post_json("/v2/scrape", body)
        self._raise_for_envelope_failure(envelope, "/v2/scrape")
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise FirecrawlError("firecrawl /v2/scrape (interact) returned no data object")
        return ScrapeResult.model_validate(data)
