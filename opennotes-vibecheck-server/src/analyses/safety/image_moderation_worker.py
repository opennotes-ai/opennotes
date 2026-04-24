from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from src.analyses.safety._schemas import ImageModerationMatch
from src.analyses.safety.vision_client import annotate_images
from src.config import Settings

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
    if not capped:
        return {"matches": []}
    async with httpx.AsyncClient() as hx:
        url_to_result = await annotate_images(
            [img for _, img in capped], httpx_client=hx
        )
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
    return {"matches": [m.model_dump() for m in matches]}
