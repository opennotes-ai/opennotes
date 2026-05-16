from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from src.url_content_scan.analyses.safety.google_client import get_access_token
from src.url_content_scan.models import UrlScanWebRiskLookup
from src.url_content_scan.normalize import canonical_cache_key
from src.url_content_scan.safety_schemas import WebRiskFinding
from src.url_content_scan.schemas import WebRiskSection
from src.utils.url_security import InvalidURL, validate_public_http_url

WEB_RISK_URL = "https://webrisk.googleapis.com/v1/uris:search"
THREAT_TYPES = (
    "MALWARE",
    "SOCIAL_ENGINEERING",
    "UNWANTED_SOFTWARE",
    "POTENTIALLY_HARMFUL_APPLICATION",
)
_LOOKUP_TTL = timedelta(hours=24)


class WebRiskClient(Protocol):
    async def check_url(self, url: str) -> WebRiskFinding | None: ...


class SessionLike(Protocol):
    async def get(
        self, model: type[UrlScanWebRiskLookup], key: str
    ) -> UrlScanWebRiskLookup | None: ...
    async def merge(self, row: UrlScanWebRiskLookup) -> UrlScanWebRiskLookup: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class GoogleWebRiskClient:
    async def check_url(self, url: str) -> WebRiskFinding | None:
        token = await get_access_token()
        if not token:
            raise RuntimeError("ADC token unavailable")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                WEB_RISK_URL,
                params={"uri": url, "threatTypes": list(THREAT_TYPES)},
                headers={"Authorization": f"Bearer {token}"},
                timeout=20.0,
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise RuntimeError(f"web-risk {response.status_code}")
        response.raise_for_status()
        threat_types = ((response.json().get("threat") or {}).get("threatTypes")) or []
        if not threat_types:
            return None
        return WebRiskFinding(url=url, threat_types=list(threat_types))


async def run_pre_enqueue_web_risk(
    url: str,
    *,
    session: SessionLike | None = None,
    web_risk_client: WebRiskClient | None = None,
    lookup_cache: dict[str, WebRiskFinding | None] | None = None,
    ttl: timedelta = _LOOKUP_TTL,
    now: datetime | None = None,
) -> WebRiskFinding | None:
    return await _lookup_url(
        url,
        session=session,
        web_risk_client=web_risk_client or GoogleWebRiskClient(),
        lookup_cache=lookup_cache,
        ttl=ttl,
        now=now or datetime.now(UTC),
    )


async def run_web_risk(
    *,
    page_url: str,
    mentioned_urls: list[str],
    media_urls: list[str],
    session: SessionLike | None = None,
    web_risk_client: WebRiskClient | None = None,
    lookup_cache: dict[str, WebRiskFinding | None] | None = None,
    ttl: timedelta = _LOOKUP_TTL,
    now: datetime | None = None,
) -> WebRiskSection:
    lookup_now = now or datetime.now(UTC)
    findings: list[WebRiskFinding] = []
    seen_normalized: set[str] = set()
    for candidate in [page_url, *mentioned_urls, *media_urls]:
        try:
            normalized = canonical_cache_key(candidate)
        except InvalidURL:
            continue
        if normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)
        finding = await _lookup_url(
            candidate,
            session=session,
            web_risk_client=web_risk_client or GoogleWebRiskClient(),
            lookup_cache=lookup_cache,
            ttl=ttl,
            now=lookup_now,
        )
        if finding is not None:
            findings.append(finding)
    return WebRiskSection(findings=findings)


async def _lookup_url(
    url: str,
    *,
    session: SessionLike | None,
    web_risk_client: WebRiskClient,
    lookup_cache: dict[str, WebRiskFinding | None] | None,
    ttl: timedelta,
    now: datetime,
) -> WebRiskFinding | None:
    safe_url = validate_public_http_url(url)
    normalized_url = canonical_cache_key(safe_url)
    if lookup_cache is not None and normalized_url in lookup_cache:
        return lookup_cache[normalized_url]

    if session is not None:
        row = await session.get(UrlScanWebRiskLookup, normalized_url)
        if row is not None and row.expires_at > now:
            finding = _finding_from_payload(row.findings)
            if lookup_cache is not None:
                lookup_cache[normalized_url] = finding
            return finding

    finding = await web_risk_client.check_url(safe_url)
    if session is not None:
        await _store_lookup(
            session,
            normalized_url=normalized_url,
            safe_url=safe_url,
            finding=finding,
            expires_at=now + ttl,
        )
    if lookup_cache is not None:
        lookup_cache[normalized_url] = finding
    return finding


async def _store_lookup(
    session: SessionLike,
    *,
    normalized_url: str,
    safe_url: str,
    finding: WebRiskFinding | None,
    expires_at: datetime,
) -> None:
    payload = (
        finding.model_dump(mode="json")
        if finding is not None
        else {
            "url": normalized_url,
            "threat_types": [],
        }
    )
    try:
        await session.merge(
            UrlScanWebRiskLookup(
                normalized_url=normalized_url,
                findings=payload,
                expires_at=expires_at,
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def _finding_from_payload(payload: dict[str, object]) -> WebRiskFinding | None:
    finding = WebRiskFinding.model_validate(payload)
    if not finding.threat_types:
        return None
    return finding
