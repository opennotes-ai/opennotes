from __future__ import annotations

from typing import Any
from uuid import UUID

from src.analyses.slot_utterances import load_job_utterances
from src.analyses.tone.flashpoint import detect_flashpoints_bulk
from src.config import Settings


async def run_flashpoint(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    del task_attempt, payload
    utterances = await load_job_utterances(pool, job_id)
    matches = await detect_flashpoints_bulk(utterances, settings)
    return {
        "flashpoint_matches": [
            match.model_dump(mode="json") for match in matches if match is not None
        ]
    }


__all__ = ["run_flashpoint"]
