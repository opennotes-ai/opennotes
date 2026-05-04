"""Async wrapper over the Firecrawl v2 HTTP API."""

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
    "we do not support this site",
)
_FIRECRAWL_UNSUPPORTED_KEYS = frozenset({"$defs", "definitions", "format"})


def _looks_like_refusal(text: str | None) -> bool:
    if not text:
        return False
    haystack = text.lower()
    return any(marker in haystack for marker in _REFUSAL_MARKERS)


def _inline_defs(schema: dict[str, Any]) -> dict[str, Any]:
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
    if fmt == "screenshot@fullPage":
        return {"type": "screenshot", "fullPage": True}
    return {"type": fmt}


class ScrapeMetadata(BaseModel):
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
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item:
                    return item
            return None
        return value


class ScrapeResult(BaseModel):
    markdown: str | None = Field(default=None)
    html: str | None = Field(default=None)
    raw_html: str | None = Field(default=None, validation_alias=AliasChoices("raw_html", "rawHtml"))
    screenshot: str | None = Field(default=None)
    links: list[str] | None = Field(default=None)
    metadata: ScrapeMetadata | None = Field(default=None)
    warning: str | None = Field(default=None)
    actions: dict[str, Any] | None = Field(default=None)
    model_config = ConfigDict(populate_by_name=True)


class FirecrawlError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FirecrawlBlocked(FirecrawlError):  # noqa: N818
    """Firecrawl refused this URL."""


class _RetryableHTTPStatusError(Exception):
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"firecrawl returned retryable status {status_code}: {body[:200]}")
        self.status_code = status_code
        self.body = body


class FirecrawlClient:
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
            data = await self._poll_extract(
                job_id, poll_interval=poll_interval, poll_timeout=poll_timeout
            )
        return schema.model_validate(data)

    async def _poll_extract(
        self, job_id: str, *, poll_interval: float, poll_timeout: float
    ) -> dict[str, Any]:
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
                raise FirecrawlError(
                    f"firecrawl /v2/extract/{job_id} polling timed out after {poll_timeout}s"
                )
            await asyncio.sleep(poll_interval)

    async def scrape(
        self,
        url: str,
        formats: list[str],
        *,
        only_main_content: bool = False,
    ) -> ScrapeResult:
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
        chosen_formats = list(formats) if formats is not None else list(_DEFAULT_INTERACT_FORMATS)
        body: dict[str, Any] = {
            "url": url,
            "actions": actions,
            "formats": [_format_to_object(fmt) for fmt in chosen_formats],
            "onlyMainContent": only_main_content,
        }
        envelope = await self._post_json("/v2/scrape", body)
        self._raise_for_envelope_failure(envelope, "/v2/scrape")
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise FirecrawlError("firecrawl /v2/scrape (interact) returned no data object")
        return ScrapeResult.model_validate(data)
