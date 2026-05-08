from __future__ import annotations

import httpx
import pytest

from src.analyses.safety.video_intelligence_client import (
    ANNOTATE_URL,
    OperationStatus,
    VIPermanentError,
    VITransientError,
    get_operation,
    parse_explicit_content,
    submit_explicit_content_annotation,
)


class _FakeHttp:
    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    async def post(self, url: str, **kwargs):
        self.requests.append(("POST", url, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def get(self, url: str, **kwargs):
        self.requests.append(("GET", url, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.mark.asyncio
async def test_submit_explicit_content_annotation_posts_gs_uri() -> None:
    http = _FakeHttp(httpx.Response(200, json={"name": "projects/p/operations/123"}))

    name = await submit_explicit_content_annotation(
        "gs://bucket/video.mp4",
        http=http,
        token="token",
    )

    assert name == "projects/p/operations/123"
    method, url, kwargs = http.requests[0]
    assert method == "POST"
    assert url == ANNOTATE_URL
    assert kwargs["json"] == {
        "inputUri": "gs://bucket/video.mp4",
        "features": ["EXPLICIT_CONTENT_DETECTION"],
    }


@pytest.mark.asyncio
async def test_get_operation_returns_pending_status() -> None:
    http = _FakeHttp(httpx.Response(200, json={"name": "operations/1"}))

    status = await get_operation("operations/1", http=http, token="token")

    assert status == OperationStatus(
        name="operations/1",
        done=False,
        error=None,
        response=None,
    )


@pytest.mark.asyncio
async def test_get_operation_classifies_network_as_transient() -> None:
    http = _FakeHttp(httpx.ConnectError("boom"))

    with pytest.raises(VITransientError):
        await get_operation("operations/1", http=http, token="token")


@pytest.mark.asyncio
async def test_submit_classifies_400_as_permanent() -> None:
    http = _FakeHttp(httpx.Response(400, text="bad uri"))

    with pytest.raises(VIPermanentError):
        await submit_explicit_content_annotation(
            "gs://bucket/video.mp4",
            http=http,
            token="token",
        )


def test_parse_explicit_content_emits_sorted_segment_findings() -> None:
    findings = parse_explicit_content(
        {
            "annotationResults": [
                {
                    "explicitAnnotation": {
                        "frames": [
                            {
                                "timeOffset": "2.500s",
                                "pornographyLikelihood": "VERY_LIKELY",
                            },
                            {
                                "timeOffset": "1.000s",
                                "pornographyLikelihood": "VERY_UNLIKELY",
                            },
                        ]
                    }
                }
            ]
        }
    )

    assert [finding.start_offset_ms for finding in findings] == [1000, 2500]
    assert findings[0].flagged is False
    assert findings[1].flagged is True
    assert findings[1].adult == 1.0
