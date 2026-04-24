from __future__ import annotations

import base64
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from src.analyses.safety._vision_likelihood import likelihood_to_score
from src.services.gcp_adc import CLOUD_PLATFORM_SCOPE, get_access_token
from src.utils.url_security import InvalidURL, validate_public_http_url

ANNOTATE_URL = "https://vision.googleapis.com/v1/images:annotate"
MAX_PER_BATCH = 16
FLAG_THRESHOLD = likelihood_to_score("LIKELY")


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
    """Auth/5xx/429/network — slot worker catches and retries."""


async def annotate_images(
    image_urls: list[str],
    *,
    httpx_client: httpx.AsyncClient,
    threshold: float = FLAG_THRESHOLD,
    max_bytes_inline: int = 4_000_000,
) -> dict[str, SafeSearchResult | None]:
    if not image_urls:
        return {}

    supported = [u for u in image_urls if urlparse(u).scheme in ("http", "https")]
    results: dict[str, SafeSearchResult | None] = {
        u: None for u in image_urls if u not in supported
    }

    token = get_access_token(CLOUD_PLATFORM_SCOPE)
    if not token:
        raise VisionTransientError("ADC token unavailable")

    failed_imageuri: list[str] = []
    for i in range(0, len(supported), MAX_PER_BATCH):
        batch = supported[i : i + MAX_PER_BATCH]
        payload = {
            "requests": [
                {
                    "image": {"source": {"imageUri": url}},
                    "features": [{"type": "SAFE_SEARCH_DETECTION"}],
                }
                for url in batch
            ]
        }
        r = await httpx_client.post(
            ANNOTATE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20.0,
        )
        if r.status_code == 429 or r.status_code >= 500:
            raise VisionTransientError(f"vision {r.status_code}")
        r.raise_for_status()
        responses = r.json().get("responses") or []
        for url, resp in zip(batch, responses, strict=False):
            if not isinstance(resp, dict):
                results[url] = None
                continue
            if resp.get("error") is not None:
                failed_imageuri.append(url)
                continue
            annotation = resp.get("safeSearchAnnotation") or {}
            results[url] = _build_result(annotation, threshold)

    for url in failed_imageuri:
        results[url] = await _retry_with_inline_bytes(
            url, httpx_client, token, threshold, max_bytes_inline
        )

    return results


def _build_result(annotation: dict[str, object], threshold: float) -> SafeSearchResult:
    scores = {
        k: likelihood_to_score(str(annotation.get(k, "UNKNOWN")))
        for k in ("adult", "violence", "racy", "medical", "spoof")
    }
    max_likelihood = max(scores.values())
    return SafeSearchResult(
        **scores,
        flagged=max_likelihood >= threshold,
        max_likelihood=max_likelihood,
    )


async def _retry_with_inline_bytes(
    url: str,
    httpx_client: httpx.AsyncClient,
    token: str,
    threshold: float,
    max_bytes: int,
) -> SafeSearchResult | None:
    # SSRF guard: the inline-bytes fallback fetches the image URL server-side.
    # Without this check, a page-supplied URL pointing at a private/internal
    # host (metadata service, localhost, RFC1918) would be fetched and forwarded
    # to Google. The primary imageUri path delegates fetch to Google so this
    # fallback is the only server-side network call that needs validation.
    try:
        safe_url = validate_public_http_url(url)
    except InvalidURL:
        return None

    try:
        async with httpx_client.stream("GET", safe_url, timeout=15.0) as r:
            if r.status_code >= 400:
                return None
            chunks: list[bytes] = []
            total = 0
            async for chunk in r.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    return None
                chunks.append(chunk)
            raw = b"".join(chunks)
    except httpx.HTTPError:
        return None

    b64 = base64.b64encode(raw).decode("ascii")
    payload = {
        "requests": [
            {
                "image": {"content": b64},
                "features": [{"type": "SAFE_SEARCH_DETECTION"}],
            }
        ]
    }
    r = await httpx_client.post(
        ANNOTATE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20.0,
    )
    if r.status_code == 429 or r.status_code >= 500:
        raise VisionTransientError(f"vision-inline {r.status_code}")
    r.raise_for_status()
    resp = (r.json().get("responses") or [{}])[0]
    if resp.get("error") is not None:
        return None
    annotation = resp.get("safeSearchAnnotation") or {}
    return _build_result(annotation, threshold)
