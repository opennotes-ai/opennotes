"""Slot-level parallel orchestrator for SAFETY__MODERATION.

Runs OpenAI and GCP Natural Language moderation in parallel via
`asyncio.gather(return_exceptions=True)`. Partial success is tolerated —
if one provider fails the other's matches are still emitted. Both failing
raises `ModerationSlotError` so the downstream slot worker can retry via
Cloud Tasks.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

import httpx
from openai import AsyncOpenAI

from src.analyses.safety.gcp_moderation import GcpModerationTransientError, moderate_texts_gcp
from src.analyses.safety.moderation import check_content_moderation_bulk
from src.config import Settings
from src.services.openai_moderation import OpenAIModerationService

logger = logging.getLogger(__name__)


class ModerationSlotError(Exception):
    """Raised when BOTH providers fail — slot worker retries via Cloud Tasks."""


async def run_safety_moderation(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings | None,
) -> dict[str, Any]:
    utterances = list(getattr(payload, "utterances", []) or [])

    moderation_service: OpenAIModerationService | None = None
    if settings is not None and getattr(settings, "OPENAI_API_KEY", ""):
        moderation_service = OpenAIModerationService(
            client=AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        )

    async with httpx.AsyncClient() as hx:
        openai_task = check_content_moderation_bulk(utterances, moderation_service)
        gcp_task = moderate_texts_gcp(utterances, httpx_client=hx)
        openai_res, gcp_res = await asyncio.gather(
            openai_task, gcp_task, return_exceptions=True
        )

    matches: list[dict[str, Any]] = []
    if isinstance(openai_res, BaseException):
        logger.warning("openai moderation failed: %s", openai_res)
    else:
        for m in openai_res:
            if m is not None:
                matches.append(m.model_dump())
    if isinstance(gcp_res, BaseException):
        logger.warning("gcp moderation failed: %s", gcp_res)
    else:
        for m in gcp_res:
            if m is not None:
                matches.append(m.model_dump())

    if isinstance(openai_res, BaseException) and isinstance(gcp_res, BaseException):
        raise ModerationSlotError(
            f"both moderation providers failed: openai={openai_res!r} gcp={gcp_res!r}"
        )
    return {"harmful_content_matches": matches}


__all__ = ["ModerationSlotError", "run_safety_moderation"]
