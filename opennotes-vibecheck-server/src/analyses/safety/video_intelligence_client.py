from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from src.analyses.safety._schemas import VideoSegmentFinding
from src.analyses.safety._vision_likelihood import likelihood_to_score
from src.analyses.safety.vision_client import FLAG_THRESHOLD
from src.monitoring import external_api_span

ANNOTATE_URL = "https://videointelligence.googleapis.com/v1/videos:annotate"
OPERATION_URL_TMPL = "https://videointelligence.googleapis.com/v1/{op_name}"


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


async def submit_explicit_content_annotation(
    gs_uri: str,
    *,
    http: Any,
    token: str,
) -> str:
    payload = {"inputUri": gs_uri, "features": ["EXPLICIT_CONTENT_DETECTION"]}
    with external_api_span("video_intelligence", "videos.annotate") as obs:
        try:
            response = await http.post(
                ANNOTATE_URL,
                headers=_headers(token),
                json=payload,
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            obs.set_error_category("network")
            raise VITransientError("video-intelligence annotate network") from exc
        _raise_for_status(response, obs, "video-intelligence annotate")
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
    with external_api_span("video_intelligence", "operations.get") as obs:
        try:
            response = await http.get(
                OPERATION_URL_TMPL.format(op_name=operation_name),
                headers=_headers(token),
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            obs.set_error_category("network")
            raise VITransientError("video-intelligence operation network") from exc
        _raise_for_status(response, obs, "video-intelligence operation")
        body = response.json()
    error = body.get("error")
    return OperationStatus(
        name=str(body.get("name") or operation_name),
        done=bool(body.get("done", False)),
        error=str(error) if error else None,
        response=body.get("response") if body.get("done") and not error else None,
    )


def parse_explicit_content(response: dict[str, Any]) -> list[VideoSegmentFinding]:
    annotation_results = response.get("annotationResults") or []
    findings: list[VideoSegmentFinding] = []
    for result in annotation_results:
        explicit = result.get("explicitAnnotation") if isinstance(result, dict) else None
        frames = explicit.get("frames") if isinstance(explicit, dict) else None
        if not isinstance(frames, list):
            continue
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            score = likelihood_to_score(
                str(frame.get("pornographyLikelihood", "UNKNOWN"))
            )
            offset_ms = _offset_ms(frame.get("timeOffset"))
            findings.append(
                VideoSegmentFinding(
                    start_offset_ms=offset_ms,
                    end_offset_ms=offset_ms,
                    adult=score,
                    violence=0.0,
                    racy=score,
                    medical=0.0,
                    spoof=0.0,
                    flagged=score >= FLAG_THRESHOLD,
                    max_likelihood=score,
                )
            )
    return sorted(findings, key=lambda item: item.start_offset_ms)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _raise_for_status(response: httpx.Response, obs: Any, prefix: str) -> None:
    obs.set_response_status(response.status_code)
    if response.status_code == 429:
        obs.set_error_category("rate_limited")
        raise VITransientError(f"{prefix} {response.status_code}")
    if response.status_code >= 500:
        obs.set_error_category("upstream")
        raise VITransientError(f"{prefix} {response.status_code}")
    if 400 <= response.status_code < 500:
        obs.set_error_category("invalid_request")
        raise VIPermanentError(f"{prefix} {response.status_code}: {response.text[:200]}")


def _offset_ms(value: Any) -> int:
    if isinstance(value, str) and value.endswith("s"):
        return int(float(value[:-1]) * 1000)
    if isinstance(value, dict):
        seconds = int(value.get("seconds") or 0)
        nanos = int(value.get("nanos") or 0)
        return seconds * 1000 + round(nanos / 1_000_000)
    return 0
