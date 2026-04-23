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
from typing import Any
from uuid import UUID

import httpx
from pydantic_ai import Agent, RunContext

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

    Pulls ``claims_report.deduped_claims`` from *payload*.  Returns early with
    an empty list when no claims are present so the agent is not invoked
    unnecessarily.

    Returns ``{"known_misinformation": [<FactCheckMatch.model_dump()>, ...]}``.
    """
    deduped_claims = _extract_deduped_claims(payload)
    if not deduped_claims:
        return {"known_misinformation": []}

    agent = build_agent(
        settings,
        output_type=list[FactCheckMatch],
        system_prompt=FACTS_AGENT_SYSTEM_PROMPT,
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

    async with httpx.AsyncClient(timeout=15.0) as hx:
        user_prompt = json.dumps(
            [
                c if isinstance(c, str) else getattr(c, "model_dump", lambda: c)()
                for c in deduped_claims
            ]
        )
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
