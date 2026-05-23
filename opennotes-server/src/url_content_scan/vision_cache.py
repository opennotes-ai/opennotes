from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, fields
from datetime import UTC, datetime, timedelta
from typing import Protocol

from src.url_content_scan.analyses.safety.vision import SafeSearchResult
from src.url_content_scan.models import UrlScanImageAnalysisCache, UrlScanVideoAnalysisCache
from src.url_content_scan.safety_schemas import FrameFinding

_KNOWN_SAFE_SEARCH_FIELDS = frozenset(f.name for f in fields(SafeSearchResult))


class SessionLike(Protocol):
    async def get(self, model: type, key: str) -> object | None: ...
    async def merge(self, row: object) -> object: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class SessionFactoryLike(Protocol):
    def __call__(self) -> AbstractAsyncContextManager[SessionLike]: ...


class VisionCache:
    """Per-URL cache for Vision API results (image SafeSearch + video frame findings).

    Image results are stored as SafeSearchResult dataclass payloads. Video results are
    stored as lists of FrameFinding model payloads. Both use SQLAlchemy sessions for
    durable storage with TTL-based expiry.
    """

    def __init__(self, *, session_factory: SessionFactoryLike) -> None:
        self._session_factory = session_factory

    async def get_image(self, image_url: str) -> SafeSearchResult | None:
        async with self._session_factory() as session:
            row: UrlScanImageAnalysisCache | None = await session.get(
                UrlScanImageAnalysisCache, image_url
            )
        if row is None:
            return None
        if row.expires_at <= datetime.now(UTC):
            return None
        payload = row.result_payload
        if isinstance(payload, str):
            payload = json.loads(payload)
        filtered = {k: v for k, v in payload.items() if k in _KNOWN_SAFE_SEARCH_FIELDS}
        return SafeSearchResult(**filtered)

    async def put_image(
        self,
        image_url: str,
        result: SafeSearchResult | None,
        *,
        ttl_hours: int,
    ) -> None:
        if result is None:
            return
        expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
        row = UrlScanImageAnalysisCache(
            image_url=image_url,
            result_payload=asdict(result),
            checked_at=datetime.now(UTC),
            expires_at=expires_at,
        )
        async with self._session_factory() as session:
            await session.merge(row)
            await session.commit()

    async def get_video(self, video_url: str) -> list[FrameFinding] | None:
        async with self._session_factory() as session:
            row: UrlScanVideoAnalysisCache | None = await session.get(
                UrlScanVideoAnalysisCache, video_url
            )
        if row is None:
            return None
        if row.expires_at <= datetime.now(UTC):
            return None
        payload = row.frame_findings_payload
        if isinstance(payload, str):
            payload = json.loads(payload)
        return [FrameFinding.model_validate(_normalize_cached_finding(f)) for f in payload]

    async def put_video(
        self,
        video_url: str,
        findings: list[FrameFinding],
        *,
        ttl_hours: int,
    ) -> None:
        if not findings:
            return
        expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
        row = UrlScanVideoAnalysisCache(
            video_url=video_url,
            frame_findings_payload=[f.model_dump() for f in findings],
            checked_at=datetime.now(UTC),
            expires_at=expires_at,
        )
        async with self._session_factory() as session:
            await session.merge(row)
            await session.commit()


def _normalize_cached_finding(payload: dict[str, object]) -> dict[str, object]:
    if "frame_offset_ms" not in payload:
        return payload
    offset = payload["frame_offset_ms"]
    return {
        **payload,
        "start_offset_ms": offset,
        "end_offset_ms": offset,
    }
