"""Video Intelligence LRO client for explicit-content annotation.

Ported from opennotes-vibecheck-server PR530 (video_intelligence_client.py)
and adapted for opennotes-server conventions.

Key classes/functions:
- submit_explicit_content_annotation: submit a GCS-staged video to VI API
- get_operation: poll a Long-Running Operation for completion
- parse_explicit_content: parse LRO response into FrameFinding list
- is_eligible_video_url: filter ineligible URLs before LRO submission (PR581)
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import ParseResult, urlparse

import httpx

from src.url_content_scan.analyses.safety.vision import FLAG_THRESHOLD, likelihood_to_score
from src.url_content_scan.safety_schemas import FrameFinding

ANNOTATE_URL = "https://videointelligence.googleapis.com/v1/videos:annotate"
OPERATION_URL_TMPL = "https://videointelligence.googleapis.com/v1/{op_name}"

_VIDEO_FILE_EXTENSIONS = frozenset(
    {
        ".avi",
        ".m3u8",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".webm",
    }
)

_VIDEO_HOSTS = frozenset(
    {
        "player.vimeo.com",
        "vimeo.com",
        "www.youtube.com",
        "youtu.be",
        "youtube.com",
    }
)

_VIDEO_HOST_SUFFIXES = (".youtube.com", ".vimeo.com")


class VITransientError(Exception):
    """429, 5xx, or network failures that should be retried."""


class VIPermanentError(Exception):
    """Stable 4xx request failures."""


@dataclass(frozen=True)
class OperationStatus:
    name: str
    done: bool
    error: str | None
    response: dict[str, Any] | None


def is_eligible_video_url(url: str) -> bool:
    """Return whether a URL is potentially a fetchable video for VI submission.

    Rejects: empty, non-HTTP(S), private/local IP ranges, and URLs without
    a recognized video extension or known video host.
    """
    if not url or not isinstance(url, str):
        return False
    parsed_result = _parse_public_http_url(url.strip())
    if parsed_result is None:
        return False
    parsed, normalized_host = parsed_result
    if _is_video_host(normalized_host):
        return True
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in _VIDEO_FILE_EXTENSIONS)


async def submit_explicit_content_annotation(
    gs_uri: str,
    *,
    http: Any,
    token: str,
) -> str:
    payload = {"inputUri": gs_uri, "features": ["EXPLICIT_CONTENT_DETECTION"]}
    try:
        response = await http.post(
            ANNOTATE_URL,
            headers=_headers(token),
            json=payload,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise VITransientError("video-intelligence annotate network") from exc
    _raise_for_status(response, "video-intelligence annotate")
    name = response.json().get("name")
    if not isinstance(name, str) or not name:
        raise VIPermanentError("video-intelligence annotate missing operation name")
    return name


async def get_operation(
    operation_name: str,
    *,
    http: Any,
    token: str,
) -> OperationStatus:
    try:
        response = await http.get(
            OPERATION_URL_TMPL.format(op_name=operation_name),
            headers=_headers(token),
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise VITransientError("video-intelligence operation network") from exc
    _raise_for_status(response, "video-intelligence operation")
    body = response.json()
    error = body.get("error")
    return OperationStatus(
        name=str(body.get("name") or operation_name),
        done=bool(body.get("done", False)),
        error=str(error) if error else None,
        response=body.get("response") if body.get("done") and not error else None,
    )


def parse_explicit_content(response: dict[str, Any]) -> list[FrameFinding]:
    """Parse a Video Intelligence LRO response into FrameFinding entries.

    Each frame in explicitAnnotation is mapped to a FrameFinding with
    pornographyLikelihood → adult score. The results are sorted by offset.
    """
    annotation_results = response.get("annotationResults") or []
    findings: list[FrameFinding] = []
    for result in annotation_results:
        if not isinstance(result, dict):
            continue
        explicit = result.get("explicitAnnotation")
        frames = explicit.get("frames") if isinstance(explicit, dict) else None
        if not isinstance(frames, list):
            continue
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            score = likelihood_to_score(str(frame.get("pornographyLikelihood", "UNKNOWN")))
            offset_ms = _offset_ms(frame.get("timeOffset"))
            findings.append(
                FrameFinding(
                    frame_offset_ms=offset_ms,
                    adult=score,
                    violence=0.0,
                    racy=score,
                    medical=0.0,
                    spoof=0.0,
                    flagged=score >= FLAG_THRESHOLD,
                    max_likelihood=score,
                )
            )
    return sorted(findings, key=lambda f: f.frame_offset_ms)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _raise_for_status(response: httpx.Response, prefix: str) -> None:
    if response.status_code == 429:
        raise VITransientError(f"{prefix} {response.status_code}")
    if response.status_code >= 500:
        raise VITransientError(f"{prefix} {response.status_code}")
    if 400 <= response.status_code < 500:
        raise VIPermanentError(f"{prefix} {response.status_code}: {response.text[:200]}")


def _offset_ms(value: Any) -> int:
    if isinstance(value, str) and value.endswith("s"):
        return int(float(value[:-1]) * 1000)
    if isinstance(value, dict):
        seconds = int(value.get("seconds") or 0)
        nanos = int(value.get("nanos") or 0)
        return seconds * 1000 + round(nanos / 1_000_000)
    return 0


def _parse_public_http_url(url: str) -> tuple[ParseResult, str] | None:
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or not _has_valid_netloc(parsed.netloc)
        or _is_private_host(host.lower())
    ):
        return None
    return parsed, host.lower()


def _has_valid_netloc(netloc: str) -> bool:
    return bool(netloc) and not any(char.isspace() or char == "\\" for char in netloc)


def _is_video_host(host: str) -> bool:
    return host in _VIDEO_HOSTS or host.endswith(_VIDEO_HOST_SUFFIXES)


def _is_private_host(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return not address.is_global
