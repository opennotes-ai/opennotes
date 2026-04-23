from __future__ import annotations

from typing import Any
from uuid import UUID

from src.analyses.claims.dedupe import dedupe_claims
from src.analyses.claims.extract import extract_claims_bulk
from src.analyses.slot_utterances import load_job_utterances
from src.config import Settings


async def run_claims_dedup(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    del task_attempt, payload
    utterances = await load_job_utterances(pool, job_id)
    per_utterance_claims = await extract_claims_bulk(utterances, settings)
    claims = [
        claim
        for utterance_claims in per_utterance_claims
        for claim in utterance_claims
    ]
    report = await dedupe_claims(claims, utterances, settings)
    return {"claims_report": report.model_dump(mode="json")}


__all__ = ["run_claims_dedup"]
