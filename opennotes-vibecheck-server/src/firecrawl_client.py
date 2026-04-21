from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

FIRECRAWL_API_BASE = "https://api.firecrawl.dev"
DEFAULT_TIMEOUT_SECONDS = 60.0
_RETRY_STATUS = {429, 500, 502, 503, 504}


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
                    return walk({k: v for k, v in target.items()})
                return {}
            return {k: walk(v) for k, v in node.items() if k not in _FIRECRAWL_UNSUPPORTED_KEYS}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


class FirecrawlError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


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
                raise FirecrawlError(
                    f"firecrawl {path} failed: {response.status_code} {response.text[:200]}",
                    status_code=response.status_code,
                )
            return response.json()

        async for attempt in self._retrying():
            with attempt:
                return await _send()
        raise FirecrawlError(f"firecrawl {path} exhausted retries")

    async def extract(
        self,
        url: str,
        schema: type[BaseModel],
        *,
        poll_interval: float = 2.0,
        poll_timeout: float = 120.0,
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
        if envelope.get("success") is False:
            raise FirecrawlError(
                f"firecrawl /v2/extract reported failure: {envelope.get('error', 'unknown')}"
            )
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
    ) -> dict[str, Any]:
        """Call Firecrawl /v2/scrape and return the `data` sub-object.

        `formats` accepts values like ["markdown", "screenshot", "screenshot@fullPage"].
        `only_main_content=True` strips nav/footer/aside from the markdown,
        which gives much cleaner content for downstream parsing.
        """
        body: dict[str, Any] = {"url": url, "formats": formats}
        if only_main_content:
            body["onlyMainContent"] = True
        envelope = await self._post_json("/v2/scrape", body)
        if envelope.get("success") is False:
            raise FirecrawlError(
                f"firecrawl /v2/scrape reported failure: {envelope.get('error', 'unknown')}"
            )
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise FirecrawlError("firecrawl /v2/scrape returned no data object")
        return data
