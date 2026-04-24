"""Known-misinformation lookup via the Google Fact Check Tools API.

Given a single deduped claim string, query
`https://factchecktools.googleapis.com/v1alpha1/claims:search` for
published fact-check articles. Authenticates via Application Default
Credentials (same Workload Identity SA that Vertex uses) — no API key
required once the Fact Check Tools API is enabled on the project.

The API is best-effort — rate limits and upstream errors return `[]`
so the broader analysis pipeline never fails just because external
fact-check coverage is unavailable.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from typing import Any

import httpx

from src.monitoring import external_api_span

from ._factcheck_schemas import FactCheckMatch

FACT_CHECK_API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
FACT_CHECK_OAUTH_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESULTS_PER_CLAIM = 5

_logger = logging.getLogger(__name__)
_creds_lock = threading.RLock()
_cached_credentials: Any = None


def _get_access_token() -> str | None:
    """Fetch an OAuth2 access token via Application Default Credentials.

    Cached at module level; refreshed on demand via google.auth.transport.Request.
    Returns None on any auth failure so the caller short-circuits to `[]`.
    """
    global _cached_credentials  # noqa: PLW0603
    try:
        from google.auth import default as google_auth_default  # noqa: PLC0415
        from google.auth.transport.requests import (  # noqa: PLC0415
            Request as GoogleAuthRequest,
        )
    except ImportError:
        _logger.warning("google-auth not installed; cannot reach Fact Check API")
        return None

    with _creds_lock:
        if _cached_credentials is None:
            try:
                creds, _project = google_auth_default(scopes=[FACT_CHECK_OAUTH_SCOPE])
            except Exception as exc:
                _logger.warning("ADC lookup failed for Fact Check API: %s", exc)
                return None
            _cached_credentials = creds

        creds = _cached_credentials
        try:
            if not getattr(creds, "valid", False):
                creds.refresh(GoogleAuthRequest())
        except Exception as exc:
            _logger.warning("Refreshing ADC token failed for Fact Check API: %s", exc)
            return None
        token = getattr(creds, "token", None)
        return token if isinstance(token, str) and token else None


def _reset_cached_credentials_for_tests() -> None:
    """Test-only helper to drop the module-level credential cache."""
    global _cached_credentials  # noqa: PLW0603
    with _creds_lock:
        _cached_credentials = None


def _parse_review_date(raw: Any) -> date | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def _extract_matches(
    claim_text: str,
    payload: dict[str, Any],
) -> list[FactCheckMatch]:
    matches: list[FactCheckMatch] = []
    for claim in payload.get("claims", []) or []:
        if not isinstance(claim, dict):
            continue
        for review in claim.get("claimReview", []) or []:
            if not isinstance(review, dict):
                continue
            publisher_blob = review.get("publisher") or {}
            publisher = ""
            if isinstance(publisher_blob, dict):
                publisher = (
                    publisher_blob.get("name")
                    or publisher_blob.get("site")
                    or ""
                )
            match = FactCheckMatch(
                claim_text=claim_text,
                publisher=publisher,
                review_title=review.get("title") or "",
                review_url=review.get("url") or "",
                textual_rating=review.get("textualRating") or "",
                review_date=_parse_review_date(review.get("reviewDate")),
            )
            matches.append(match)
            if len(matches) >= MAX_RESULTS_PER_CLAIM:
                return matches
    return matches


async def check_known_misinformation(  # noqa: PLR0911
    claim_text: str,
    *,
    httpx_client: httpx.AsyncClient,
    language_code: str = "en",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[FactCheckMatch]:
    """Look up published fact-checks for a single deduped claim.

    Authenticates via Application Default Credentials — on Cloud Run the
    vibecheck-server SA is used (Fact Check Tools API must be enabled on
    the project). No API key.

    Returns up to `MAX_RESULTS_PER_CLAIM` matches. Rate-limit (429),
    other HTTP errors, and network failures are swallowed with a
    logged warning so the analysis pipeline keeps moving — external
    fact-check coverage is best-effort, not load-bearing.
    """
    if not claim_text.strip():
        return []

    access_token = _get_access_token()
    if access_token is None:
        return []

    params = {
        "query": claim_text,
        "languageCode": language_code,
        "pageSize": MAX_RESULTS_PER_CLAIM,
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    with external_api_span("factcheck", "claims.search", page_size=MAX_RESULTS_PER_CLAIM) as obs:
        try:
            response = await httpx_client.get(
                FACT_CHECK_API_URL,
                params=params,
                headers=headers,
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            obs.set_error_category("network")
            _logger.warning(
                "Google Fact Check API request failed for claim %r: %s",
                claim_text[:80],
                exc,
            )
            return []

        obs.set_response_status(response.status_code)
        if response.status_code >= 400:
            if response.status_code == 429:
                obs.set_error_category("rate_limited")
                _logger.warning(
                    "Google Fact Check API rate-limited (429) for claim %r; "
                    "returning no matches",
                    claim_text[:80],
                )
            else:
                obs.set_error_category("upstream")
                _logger.warning(
                    "Google Fact Check API returned HTTP %s for claim %r: %s",
                    response.status_code,
                    claim_text[:80],
                    response.text[:200],
                )
            return []

        try:
            payload = response.json()
        except ValueError as exc:
            obs.set_error_category("invalid_response")
            _logger.warning(
                "Google Fact Check API returned non-JSON body for claim %r: %s",
                claim_text[:80],
                exc,
            )
            return []

        if not isinstance(payload, dict):
            obs.set_error_category("invalid_response")
            return []

        matches = _extract_matches(claim_text, payload)
        obs.add_flagged(len(matches))
        return matches
