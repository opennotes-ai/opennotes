"""Facts agent: pydantic-ai Agent wrapping check_known_misinformation as a tool.

The agent receives a JSON-serialised list of deduped claims and decides which
ones are concrete and verifiable enough to warrant a fact-check lookup.  For
qualifying claims it calls the ``check_known_misinformation`` tool; results
from all tool calls are unioned and returned as the agent output.

Tool failures return ``[]`` and are logged as warnings — they must not fail
the agent run.  Vertex/agent-level errors propagate to the caller.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

import httpx
from pydantic_ai import RunContext

from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.claims.known_misinfo import check_known_misinformation
from src.config import Settings
from src.services.gemini_agent import build_agent

logger = logging.getLogger(__name__)

FACTS_AGENT_SYSTEM_PROMPT = """You review a list of deduped factual claims extracted from a scraped page.
For each claim, decide whether it is (a) concrete and verifiable and (b) likely to have
published fact-check coverage. For qualifying claims only, call the
check_known_misinformation tool with the exact claim text. Do NOT call the tool
for opinions, value judgments, untestable assertions, or trivially true statements.
Return the union of all matches the tool returned."""


@dataclass
class FactsAgentDeps:
    httpx_client: httpx.AsyncClient


async def run_facts_claims_known_misinfo(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    """Slot worker: look up known misinformation for deduped claims.

    Claim source (codex P1.6):
      1. If *payload* carries a ``claims_report``, use that directly.
      2. Else, read the FACTS_CLAIMS_DEDUP slot from the job's sections
         JSONB (the orchestrator passes the raw ``UtterancesPayload`` to
         every slot, so the dedup output only lives in the DB at this point).
      3. Else, return empty. Empty is treated as "no claims worth checking"
         rather than an error so a missing-dedup race yields no-op instead
         of poisoning the slot with a false failure.
    """
    deduped_claims = _extract_deduped_claims(payload)
    if not deduped_claims:
        deduped_claims = await _load_deduped_claims_from_dedup_slot(pool, job_id)
    if not deduped_claims:
        return {"known_misinformation": []}

    agent = cast(
        Any,
        build_agent(
            settings,
            output_type=cast(Any, list[FactCheckMatch]),
            system_prompt=FACTS_AGENT_SYSTEM_PROMPT,
            name="vibecheck.facts",
        ),
    )

    @agent.tool
    async def check_known_misinformation_tool(
        ctx: RunContext[FactsAgentDeps], claim_text: str
    ) -> list[FactCheckMatch]:
        try:
            return await check_known_misinformation(
                claim_text, httpx_client=ctx.deps.httpx_client
            )
        except Exception as exc:
            logger.warning("fact check tool failed for %r: %s", claim_text, exc)
            return []

    async with httpx.AsyncClient(timeout=30.0) as hx:
        serializable_claims: list[Any] = []
        for claim in deduped_claims:
            if isinstance(claim, str):
                serializable_claims.append(claim)
            elif hasattr(claim, "model_dump"):
                serializable_claims.append(claim.model_dump())
            else:
                serializable_claims.append(claim)
        user_prompt = json.dumps(serializable_claims)
        result = await agent.run(user_prompt, deps=FactsAgentDeps(httpx_client=hx))

    matches = list(result.output or [])
    return {"known_misinformation": [m.model_dump() for m in matches]}


def _extract_deduped_claims(payload: Any) -> list[Any]:
    """Extract deduped_claims from a payload carrying a claims_report.

    Returns an empty list when the payload has no ``claims_report`` attribute
    or when ``claims_report.deduped_claims`` is absent or falsy.
    """
    claims_report = getattr(payload, "claims_report", None)
    if claims_report is None:
        return []
    return list(getattr(claims_report, "deduped_claims", []) or [])


async def _load_deduped_claims_from_dedup_slot(
    pool: Any, job_id: UUID
) -> list[Any]:
    """Read FACTS_CLAIMS_DEDUP slot data from the job's sections JSONB.

    The orchestrator runs all slots in parallel with the same ``UtterancesPayload``
    input, so the dedup step's output (a ClaimsReport) lives only in the
    ``vibecheck_jobs.sections`` column until finalize stitches the sidebar.
    Return an empty list if the slot is absent, not yet done, or malformed —
    the caller treats that as "no claims to check".
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT sections -> $2 AS dedup FROM vibecheck_jobs WHERE job_id = $1",
                job_id,
                "facts_claims__dedup",
            )
    except Exception as exc:
        logger.warning("facts_agent: failed to read dedup slot: %s", exc)
        return []
    if row is None or row["dedup"] is None:
        return []
    raw = row["dedup"]
    if isinstance(raw, str):
        raw = json.loads(raw)
    data = raw.get("data") if isinstance(raw, dict) else None
    claims_report = data.get("claims_report") if isinstance(data, dict) else None
    if not isinstance(claims_report, dict):
        return []
    return list(claims_report.get("deduped_claims") or [])
