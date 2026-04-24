from __future__ import annotations

from typing import Any
from uuid import UUID

from src.analyses.opinions.subjective import extract_subjective_claims_bulk
from src.analyses.slot_utterances import load_job_utterances
from src.config import Settings


async def run_subjective(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    del task_attempt, payload
    utterances = await load_job_utterances(pool, job_id)
    per_utterance_claims = await extract_subjective_claims_bulk(
        utterances, settings=settings
    )
    claims = [
        claim.model_dump(mode="json")
        for utterance_claims in per_utterance_claims
        for claim in utterance_claims
    ]
    return {"subjective_claims": claims}


__all__ = ["run_subjective"]
