from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.url_content_scan.analyses.safety.vision import SafeSearchResult

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _make_result(*, flagged: bool = False, max_likelihood: float = 0.1) -> SafeSearchResult:
    return SafeSearchResult(
        adult=0.0,
        violence=max_likelihood if flagged else 0.0,
        racy=0.0,
        medical=0.0,
        spoof=0.0,
        flagged=flagged,
        max_likelihood=max_likelihood,
    )


def _make_neutral_result() -> SafeSearchResult:
    return SafeSearchResult(
        adult=0.0,
        violence=0.0,
        racy=0.0,
        medical=0.0,
        spoof=0.0,
        flagged=False,
        max_likelihood=0.0,
    )


class _FakeRow:
    def __init__(self, result: SafeSearchResult, expires_at: datetime) -> None:
        self.result_payload = _row_payload(result)
        self.image_url = "https://cdn.example.com/image.png"
        self.expires_at = expires_at


def _row_payload(result: SafeSearchResult) -> dict[str, object]:
    from dataclasses import asdict

    return asdict(result)


class _FakeVideoRow:
    def __init__(self, findings: list[dict], expires_at: datetime) -> None:
        self.frame_findings_payload = findings
        self.video_url = "https://cdn.example.com/clip.mp4"
        self.expires_at = expires_at


class _FakeSession:
    def __init__(self, row=None) -> None:
        self._row = row
        self.merged = []
        self.committed = 0

    async def get(self, model, key):
        return self._row

    async def merge(self, row):
        self.merged.append(row)
        return row

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        pass


class _FakeSessionFactory:
    def __init__(self, row=None) -> None:
        self._row = row
        self.session = _FakeSession(row)

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


async def test_image_cache_hit_returns_result_without_api_call():
    from src.url_content_scan.vision_cache import VisionCache

    stored_result = _make_result(flagged=True, max_likelihood=0.85)
    future = datetime.now(UTC) + timedelta(hours=1)

    class _FakeImageRow:
        def __init__(self):
            from dataclasses import asdict

            self.result_payload = asdict(stored_result)
            self.expires_at = future

    session_factory = _FakeSessionFactory(row=_FakeImageRow())
    cache = VisionCache(session_factory=session_factory)

    api_called = False

    async def _never_called(image_bytes: bytes) -> SafeSearchResult | None:
        nonlocal api_called
        api_called = True
        return None

    result = await cache.get_image("https://cdn.example.com/image.png")
    assert result is not None
    assert result.flagged is True
    assert result.max_likelihood == 0.85
    assert not api_called


async def test_image_cache_miss_returns_none():
    from src.url_content_scan.vision_cache import VisionCache

    session_factory = _FakeSessionFactory(row=None)
    cache = VisionCache(session_factory=session_factory)

    result = await cache.get_image("https://cdn.example.com/missing.png")
    assert result is None


async def test_image_cache_expired_row_returns_none():
    from src.url_content_scan.vision_cache import VisionCache

    stored_result = _make_result(flagged=True, max_likelihood=0.85)
    past = datetime.now(UTC) - timedelta(hours=1)

    class _ExpiredImageRow:
        def __init__(self):
            from dataclasses import asdict

            self.result_payload = asdict(stored_result)
            self.expires_at = past

    session_factory = _FakeSessionFactory(row=_ExpiredImageRow())
    cache = VisionCache(session_factory=session_factory)

    result = await cache.get_image("https://cdn.example.com/image.png")
    assert result is None


async def test_image_cache_put_stores_result():
    from src.url_content_scan.vision_cache import VisionCache

    session_factory = _FakeSessionFactory(row=None)
    cache = VisionCache(session_factory=session_factory)

    stored_result = _make_result(flagged=False, max_likelihood=0.2)
    await cache.put_image("https://cdn.example.com/image.png", stored_result, ttl_hours=24)

    assert session_factory.session.committed == 1
    assert len(session_factory.session.merged) == 1


async def test_image_cache_put_skips_none_result():
    from src.url_content_scan.vision_cache import VisionCache

    session_factory = _FakeSessionFactory(row=None)
    cache = VisionCache(session_factory=session_factory)

    await cache.put_image("https://cdn.example.com/image.png", None, ttl_hours=24)
    assert session_factory.session.committed == 0


async def test_video_cache_miss_returns_none():
    from src.url_content_scan.vision_cache import VisionCache

    session_factory = _FakeSessionFactory(row=None)
    cache = VisionCache(session_factory=session_factory)

    result = await cache.get_video("https://cdn.example.com/clip.mp4")
    assert result is None


async def test_video_cache_expired_row_returns_none():
    from src.url_content_scan.vision_cache import VisionCache

    past = datetime.now(UTC) - timedelta(hours=1)

    class _ExpiredVideoRow:
        def __init__(self):
            self.frame_findings_payload = []
            self.expires_at = past

    session_factory = _FakeSessionFactory(row=_ExpiredVideoRow())
    cache = VisionCache(session_factory=session_factory)

    result = await cache.get_video("https://cdn.example.com/clip.mp4")
    assert result is None


async def test_video_cache_hit_returns_findings():
    from src.url_content_scan.vision_cache import VisionCache

    future = datetime.now(UTC) + timedelta(hours=1)

    class _ValidVideoRow:
        def __init__(self):
            self.frame_findings_payload = [
                {
                    "frame_offset_ms": 0,
                    "adult": 0.0,
                    "violence": 0.8,
                    "racy": 0.0,
                    "medical": 0.0,
                    "spoof": 0.0,
                    "flagged": True,
                    "max_likelihood": 0.8,
                }
            ]
            self.expires_at = future

    session_factory = _FakeSessionFactory(row=_ValidVideoRow())
    cache = VisionCache(session_factory=session_factory)

    findings = await cache.get_video("https://cdn.example.com/clip.mp4")
    assert findings is not None
    assert len(findings) == 1
    assert findings[0].flagged is True
    assert findings[0].max_likelihood == 0.8


async def test_video_cache_put_stores_findings():
    from src.url_content_scan.safety_schemas import FrameFinding
    from src.url_content_scan.vision_cache import VisionCache

    session_factory = _FakeSessionFactory(row=None)
    cache = VisionCache(session_factory=session_factory)

    findings = [
        FrameFinding(
            frame_offset_ms=0,
            adult=0.0,
            violence=0.8,
            racy=0.0,
            medical=0.0,
            spoof=0.0,
            flagged=True,
            max_likelihood=0.8,
        )
    ]
    await cache.put_video("https://cdn.example.com/clip.mp4", findings, ttl_hours=24)

    assert session_factory.session.committed == 1


async def test_4xx_vision_response_returns_neutral_result_not_error():
    from src.url_content_scan.analyses.safety.vision import annotate_image_bytes

    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.json.return_value = {}

    mock_client = MagicMock()

    async def _post_403(*args, **kwargs):
        return mock_response

    mock_client.post = _post_403
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    result = await annotate_image_bytes(
        b"fake-image-bytes",
        http_client=mock_client,
        access_token="fake-token",
    )
    assert result is None
