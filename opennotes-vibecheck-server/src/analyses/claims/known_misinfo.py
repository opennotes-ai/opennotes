"""Known-misinformation lookup via the Google Fact Check Tools API.

Given a single deduped claim string, query
`https://factchecktools.googleapis.com/v1alpha1/claims:search` for
published fact-check articles. Map each returned `claimReview` entry to
a `FactCheckMatch`. The API is best-effort — rate limits and upstream
errors return `[]` so the broader analysis pipeline never fails just
because external fact-check coverage is unavailable.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx

from ._factcheck_schemas import FactCheckMatch

FACT_CHECK_API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESULTS_PER_CLAIM = 5

_logger = logging.getLogger(__name__)


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


async def check_known_misinformation(
    claim_text: str,
    *,
    httpx_client: httpx.AsyncClient,
    api_key: str,
    language_code: str = "en",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[FactCheckMatch]:
    """Look up published fact-checks for a single deduped claim.

    Returns up to `MAX_RESULTS_PER_CLAIM` matches. Rate-limit (429),
    other HTTP errors, and network failures are swallowed with a
    logged warning so the analysis pipeline keeps moving — external
    fact-check coverage is best-effort, not load-bearing.
    """
    if not claim_text.strip() or not api_key:
        return []

    params = {
        "query": claim_text,
        "key": api_key,
        "languageCode": language_code,
        "pageSize": MAX_RESULTS_PER_CLAIM,
    }

    try:
        response = await httpx_client.get(
            FACT_CHECK_API_URL,
            params=params,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        _logger.warning(
            "Google Fact Check API request failed for claim %r: %s",
            claim_text[:80],
            exc,
        )
        return []

    if response.status_code >= 400:
        if response.status_code == 429:
            _logger.warning(
                "Google Fact Check API rate-limited (429) for claim %r; returning no matches",
                claim_text[:80],
            )
        else:
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
        _logger.warning(
            "Google Fact Check API returned non-JSON body for claim %r: %s",
            claim_text[:80],
            exc,
        )
        return []

    if not isinstance(payload, dict):
        return []

    return _extract_matches(claim_text, payload)
