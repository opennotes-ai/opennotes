"""Flashpoint detection capabilities for vibecheck utterances.

Two entry points:

- ``detect_flashpoints_bulk(utterances, settings)`` — ONE pydantic-ai +
  Vertex Gemini call across the whole conversation. Returns a list of
  ``FlashpointMatch | None`` index-aligned with input utterances. This
  is what the orchestrator uses; keeps us well below Vertex burst quotas.

- ``detect_flashpoint(utterance, context, service)`` — legacy single-
  utterance DSPy path retained for back-compat and targeted tests. Not
  used by the orchestrator anymore.

Bulk path assumes the ordered utterance list IS the conversation context:
utterances[:i] is the prior context for utterances[i].
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.analyses.tone._flashpoint_schemas import (
    FlashpointMatch,
    RiskLevel,
    _BulkFlashpointLLM,
)
from src.config import Settings
from src.monitoring import get_logger
from src.services.gemini_agent import build_agent
from src.utterances.schema import Utterance

if TYPE_CHECKING:
    from src.services.flashpoint_service import FlashpointDetectionService

logger = get_logger(__name__)

_BULK_SYSTEM_PROMPT = (
    "You evaluate an ordered conversation for flashpoint / derailment "
    "moments — messages where the tone turns hostile, dismissive, or "
    "destructive relative to the prior context.\n\n"
    "For each numbered utterance below, return a `_FlashpointLLM` with:\n"
    "- utterance_index matching the [#] in the input\n"
    "- derailment_score: 0-100 integer where 0 = cordial, 100 = extreme hostility\n"
    "- risk_level: Low Risk | Guarded | Heated | Hostile | Dangerous\n"
    "- reasoning: ONE short sentence justifying the call; empty string if not notable\n\n"
    "The FIRST utterance has no prior context — score it 0, risk_level 'Low Risk' "
    "unless the text itself is explicitly incendiary (then still score on merit). "
    "Later utterances are scored relative to everything before them. Return EXACTLY "
    "one entry per input utterance, in input order."
)


def _format_utterance(u: Utterance) -> str:
    who = u.author or u.utterance_id or "unknown"
    return f"{who}: {u.text}"


async def detect_flashpoints_bulk(
    utterances: list[Utterance],
    settings: Settings,
    *,
    score_threshold: int = 50,
) -> list[FlashpointMatch | None]:
    """Score every utterance for flashpoint risk in ONE LLM call.

    Returns a list index-aligned with ``utterances``. Each slot is a
    ``FlashpointMatch`` when the model's ``derailment_score`` meets
    ``score_threshold``, else ``None``. Errors from the LLM short-circuit
    to all-None (logged) so the orchestrator can still ship a partial
    SidebarPayload.
    """
    out: list[FlashpointMatch | None] = [None for _ in utterances]
    if len(utterances) <= 1:
        # No prior context for a single utterance — no flashpoint possible.
        return out

    numbered: list[str] = []
    for i, u in enumerate(utterances):
        text = (u.text or "").strip()
        if not text:
            continue
        numbered.append(f"[{i}] {_format_utterance(u)}")
    if not numbered:
        return out

    agent = build_agent(
        settings,
        output_type=_BulkFlashpointLLM,
        system_prompt=_BULK_SYSTEM_PROMPT,
        name="vibecheck.flashpoint",
    )
    try:
        result = await agent.run("Conversation:\n" + "\n".join(numbered))
    except Exception as exc:
        logger.warning("bulk flashpoint detection failed: %s", exc)
        return out
    parsed: _BulkFlashpointLLM = result.output

    for entry in parsed.results:
        idx = entry.utterance_index
        if not (0 <= idx < len(utterances)):
            continue
        if entry.derailment_score < score_threshold:
            continue
        u = utterances[idx]
        out[idx] = FlashpointMatch(
            utterance_id=u.utterance_id or "",
            derailment_score=entry.derailment_score,
            risk_level=RiskLevel(entry.risk_level),
            reasoning=entry.reasoning,
            context_messages=idx,  # everything before this utterance
        )
    return out


async def detect_flashpoint(
    utterance: Utterance,
    context: list[Utterance],
    service: FlashpointDetectionService | None,
) -> FlashpointMatch | None:
    """Run flashpoint detection on a single utterance.

    Args:
        utterance: The utterance to analyze.
        context: Prior-in-time utterances in the same thread. For blog
            posts this is empty and the function short-circuits to None.
        service: A configured ``FlashpointDetectionService``, or ``None``
            if flashpoint detection is disabled for this deployment.

    Returns:
        ``FlashpointMatch`` when derailment score meets the service
        threshold, otherwise ``None``.
    """
    if service is None:
        logger.debug(
            "Flashpoint service not configured; skipping utterance_id=%s",
            utterance.utterance_id,
        )
        return None

    if not context:
        logger.debug(
            "Empty context (standalone utterance); skipping flashpoint "
            "detection utterance_id=%s kind=%s",
            utterance.utterance_id,
            utterance.kind,
        )
        return None

    try:
        return await service.detect_flashpoint(
            utterance=utterance,
            context=context,
        )
    except Exception as e:
        logger.warning(
            "Error in flashpoint detection capability utterance_id=%s: %s: %s",
            utterance.utterance_id,
            type(e).__name__,
            e,
        )
        return None
