from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from src.url_content_scan.analyses.safety.vision import (
    SafeSearchResult,
    annotate_image_bytes,
    fetch_image_bytes,
)
from src.url_content_scan.safety_schemas import ImageModerationMatch
from src.url_content_scan.schemas import ImageModerationSection


@dataclass(frozen=True)
class MentionedImage:
    utterance_id: str
    image_url: str


FetchBytes = Callable[[str], Awaitable[bytes | None]]
SafeSearch = Callable[[bytes], Awaitable[SafeSearchResult | None]]


async def run_image_moderation(
    mentioned_images: list[MentionedImage],
    *,
    fetch_bytes: FetchBytes | None = None,
    safe_search: SafeSearch | None = None,
    content_cache: dict[str, SafeSearchResult | None] | None = None,
) -> ImageModerationSection:
    if not mentioned_images:
        return ImageModerationSection()

    if fetch_bytes is None or safe_search is None:
        async with httpx.AsyncClient() as http_client:
            return await run_image_moderation(
                mentioned_images,
                fetch_bytes=lambda image_url: fetch_image_bytes(image_url, http_client=http_client),
                safe_search=lambda image_bytes: annotate_image_bytes(
                    image_bytes, http_client=http_client
                ),
                content_cache=content_cache,
            )

    cache = content_cache if content_cache is not None else {}
    matches: list[ImageModerationMatch] = []
    for item in mentioned_images:
        image_bytes = await fetch_bytes(item.image_url)
        if not image_bytes:
            continue
        content_hash = hashlib.sha256(image_bytes).hexdigest()
        if content_hash not in cache:
            cache[content_hash] = await safe_search(image_bytes)
        result = cache[content_hash]
        if result is None:
            continue
        matches.append(
            ImageModerationMatch(
                utterance_id=item.utterance_id,
                image_url=item.image_url,
                adult=result.adult,
                violence=result.violence,
                racy=result.racy,
                medical=result.medical,
                spoof=result.spoof,
                flagged=result.flagged,
                max_likelihood=result.max_likelihood,
            )
        )

    return ImageModerationSection(matches=matches)
