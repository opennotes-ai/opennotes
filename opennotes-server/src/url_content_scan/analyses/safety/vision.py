from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from src.url_content_scan.analyses.safety.google_client import get_access_token
from src.utils.url_security import InvalidURL, validate_public_http_url

ANNOTATE_URL = "https://vision.googleapis.com/v1/images:annotate"
FLAG_THRESHOLD = 0.75
_MAX_INLINE_BYTES = 4_000_000
_SCORE_MAP: dict[str, float] = {
    "UNKNOWN": 0.5,
    "VERY_UNLIKELY": 0.0,
    "UNLIKELY": 0.25,
    "POSSIBLE": 0.5,
    "LIKELY": 0.75,
    "VERY_LIKELY": 1.0,
}


@dataclass(frozen=True)
class SafeSearchResult:
    adult: float
    violence: float
    racy: float
    medical: float
    spoof: float
    flagged: bool
    max_likelihood: float


class VisionTransientError(Exception):
    pass


def likelihood_to_score(level: str) -> float:
    return _SCORE_MAP.get(level.upper(), 0.0)


async def fetch_image_bytes(
    image_url: str,
    *,
    http_client: httpx.AsyncClient | None = None,
    max_bytes: int = _MAX_INLINE_BYTES,
) -> bytes | None:
    try:
        safe_url = validate_public_http_url(image_url)
    except InvalidURL:
        return None

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient()
    try:
        async with client.stream("GET", safe_url, timeout=30.0) as response:
            if response.status_code >= 400:
                return None
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    return None
                chunks.append(chunk)
        return b"".join(chunks)
    except httpx.HTTPError:
        return None
    finally:
        if owns_client:
            await client.aclose()


async def annotate_image_bytes(
    image_bytes: bytes,
    *,
    http_client: httpx.AsyncClient | None = None,
    access_token: str | None = None,
    threshold: float = FLAG_THRESHOLD,
) -> SafeSearchResult | None:
    token = access_token or await get_access_token()
    if not token:
        raise VisionTransientError("ADC token unavailable")

    payload = {
        "requests": [
            {
                "image": {"content": base64.b64encode(image_bytes).decode("ascii")},
                "features": [{"type": "SAFE_SEARCH_DETECTION"}],
            }
        ]
    }
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient()
    try:
        response = await client.post(
            ANNOTATE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=40.0,
        )
    except httpx.HTTPError as exc:
        raise VisionTransientError("vision network") from exc
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code == 429 or response.status_code >= 500:
        raise VisionTransientError(f"vision {response.status_code}")
    response.raise_for_status()
    item = ((response.json().get("responses") or [{}])[0]) or {}
    if item.get("error") is not None:
        return None
    return build_result(item.get("safeSearchAnnotation") or {}, threshold=threshold)


def build_result(
    annotation: dict[str, object], *, threshold: float = FLAG_THRESHOLD
) -> SafeSearchResult:
    scores = {
        key: likelihood_to_score(str(annotation.get(key, "UNKNOWN")))
        for key in ("adult", "violence", "racy", "medical", "spoof")
    }
    max_likelihood = max(scores.values(), default=0.0)
    return SafeSearchResult(
        adult=scores["adult"],
        violence=scores["violence"],
        racy=scores["racy"],
        medical=scores["medical"],
        spoof=scores["spoof"],
        flagged=max_likelihood >= threshold,
        max_likelihood=max_likelihood,
    )
