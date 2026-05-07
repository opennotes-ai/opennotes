from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
import logfire

from src.analyses.safety._schemas import ImageModerationMatch
from src.analyses.safety.vision_client import SafeSearchResult, annotate_images
from src.cache import image_analysis_cache
from src.config import Settings
from src.monitoring_metrics import SECTION_MEDIA_DROPPED

logger = logging.getLogger(__name__)


async def run_image_moderation(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    pairs: list[tuple[str, str]] = []
    for utt in getattr(payload, "utterances", []) or []:
        for img in getattr(utt, "mentioned_images", []) or []:
            pairs.append((utt.utterance_id or "", img))
    capped = pairs[: settings.MAX_IMAGES_MODERATED]
    dropped = len(pairs) - len(capped)
    if dropped > 0:
        logger.info(
            "image moderation cap: processing=%d dropped=%d", len(capped), dropped
        )
        SECTION_MEDIA_DROPPED.labels(media_type="image").inc(dropped)
    with logfire.span(
        "vibecheck.section.image_moderation",
        image_count=len(capped),
        dropped_image_count=dropped,
    ) as span:
        if not capped:
            return {"matches": []}
        image_urls = [img for _, img in capped]
        try:
            cached = await image_analysis_cache.fetch_cached(pool, image_urls)
        except Exception:
            logger.exception("image cache fetch_cached failed; bypassing cache")
            cached = {}
        # Dedupe so duplicate URLs across utterances hit the API once.
        missing = list(dict.fromkeys(u for u in image_urls if u not in cached))
        fresh: dict[str, SafeSearchResult | None] = {}
        if missing:
            async with httpx.AsyncClient() as hx:
                fresh = await annotate_images(missing, httpx_client=hx)
            try:
                await image_analysis_cache.upsert_cached(
                    pool, fresh, ttl_hours=settings.VISION_IMAGE_CACHE_TTL_HOURS
                )
            except Exception:
                logger.exception("image cache upsert_cached failed; results not persisted")
        url_to_result: dict[str, SafeSearchResult | None] = {**cached, **fresh}
        span.set_attribute("cache_hit_count", len(cached))
        matches: list[ImageModerationMatch] = []
        for uid, img in capped:
            result = url_to_result.get(img)
            if result is None:
                continue
            matches.append(ImageModerationMatch(
                utterance_id=uid,
                image_url=img,
                adult=result.adult,
                violence=result.violence,
                racy=result.racy,
                medical=result.medical,
                spoof=result.spoof,
                flagged=result.flagged,
                max_likelihood=result.max_likelihood,
            ))
        span.set_attribute("flagged_count", sum(1 for match in matches if match.flagged))
        return {"matches": [m.model_dump() for m in matches]}
