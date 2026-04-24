from __future__ import annotations

from typing import Any
from uuid import UUID

from src.analyses.opinions.sentiment import compute_sentiment_stats
from src.analyses.slot_utterances import load_job_utterances
from src.config import Settings


async def run_sentiment(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    del task_attempt, payload
    utterances = await load_job_utterances(pool, job_id)
    report = await compute_sentiment_stats(utterances, settings=settings)
    return {"sentiment_stats": report.model_dump(mode="json")}


__all__ = ["run_sentiment"]
