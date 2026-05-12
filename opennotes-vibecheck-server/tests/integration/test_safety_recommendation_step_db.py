"""Integration coverage for safety recommendation source_url propagation and
same-page Web Risk prefiltering in the orchestrator step (TASK-1609.06/07)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

from src.analyses.safety._schemas import (
    Divergence,
    SafetyLevel,
    SafetyRecommendation,
)
from src.analyses.schemas import SectionSlug, SectionState

from .conftest import insert_pending_job, read_job


def _seed_safety_sections() -> dict[str, Any]:
    moderation_slot_attempt = uuid4()
    web_risk_slot_attempt = uuid4()
    image_slot_attempt = uuid4()
    video_slot_attempt = uuid4()

    return {
        SectionSlug.SAFETY_MODERATION.value: {
            "state": SectionState.DONE.value,
            "attempt_id": str(moderation_slot_attempt),
            "data": {
                "harmful_content_matches": [
                    {
                        "utterance_id": "u1",
                        "utterance_text": "harmful text",
                        "max_score": 0.91,
                        "categories": {"harassment": True},
                        "scores": {"harassment": 0.91},
                        "flagged_categories": ["harassment"],
                        "source": "openai",
                    }
                ]
            },
            "error": None,
            "started_at": None,
            "finished_at": None,
        },
        SectionSlug.SAFETY_WEB_RISK.value: {
            "state": SectionState.DONE.value,
            "attempt_id": str(web_risk_slot_attempt),
            "data": {
                "findings": [
                    {
                        "url": "https://example.com/article",
                        "threat_types": ["MALWARE"],
                    },
                    {
                        "url": "https://example.com/other",
                        "threat_types": ["SOCIAL_ENGINEERING"],
                    },
                ]
            },
            "error": None,
            "started_at": None,
            "finished_at": None,
        },
        SectionSlug.SAFETY_IMAGE_MODERATION.value: {
            "state": SectionState.DONE.value,
            "attempt_id": str(image_slot_attempt),
            "data": {"matches": []},
            "error": None,
            "started_at": None,
            "finished_at": None,
        },
        SectionSlug.SAFETY_VIDEO_MODERATION.value: {
            "state": SectionState.DONE.value,
            "attempt_id": str(video_slot_attempt),
            "data": {"matches": []},
            "error": None,
            "started_at": None,
            "finished_at": None,
        },
    }


async def test_run_safety_recommendation_step_writes_db_prefilter_and_merges_divergences(
    db_pool: Any,
    monkeypatch,
) -> None:
    from src.jobs import orchestrator

    job_url = "https://example.com/article?utm_source=campaign"
    job_id, task_attempt = await insert_pending_job(
        db_pool, url=job_url, attempt_id=uuid4()
    )
    sections = _seed_safety_sections()

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET sections = $1, status = 'analyzing' WHERE job_id = $2",
            json.dumps(sections),
            job_id,
        )

    captured_inputs: list[Any] = []
    final_divergence_logs: list[dict[str, Any]] = []

    async def fake_run_safety_recommendation(inputs, settings):
        captured_inputs.append(inputs)
        return SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="Baseline review passed.",
            top_signals=["WebRisk mismatch retained."],
            divergences=[
                Divergence(
                    direction="escalated",
                    signal_source="Web Risk",
                    signal_detail="External social engineering risk detected.",
                    reason="Found a high-confidence different-page Web Risk match.",
                )
            ],
        )

    def fake_logfire_info(message: str, **attrs: Any) -> None:
        if message == "safety_recommendation_final_divergences":
            final_divergence_logs.append(attrs)

    monkeypatch.setattr(
        orchestrator, "run_safety_recommendation", fake_run_safety_recommendation
    )
    monkeypatch.setattr(orchestrator.logfire, "info", fake_logfire_info)

    await orchestrator._run_safety_recommendation_step(
        db_pool, job_id, task_attempt, MagicMock()
    )

    row = await read_job(db_pool, job_id)
    recommendation = row["safety_recommendation"]
    if isinstance(recommendation, str):
        recommendation = json.loads(recommendation)
    assert recommendation is not None
    assert row["url"] == job_url
    assert captured_inputs, "run_safety_recommendation must receive SafetyRecommendationInputs"
    assert captured_inputs[0].source_url == job_url
    assert [finding.url for finding in captured_inputs[0].web_risk_findings] == [
        "https://example.com/other",
    ]
    assert recommendation["divergences"] == [
        {
            "direction": "escalated",
            "signal_source": "Web Risk",
            "signal_detail": "External social engineering risk detected.",
            "reason": "Found a high-confidence different-page Web Risk match.",
        },
        {
            "direction": "discounted",
            "signal_source": "Web Risk",
            "signal_detail": "Same-page URL",
            "reason": "The flagged URL is the same page under analysis.",
        },
    ]
    assert final_divergence_logs == [
        {
            "synthesized_divergence_count": 1,
            "divergence_count": 2,
            "divergence_direction_distribution": {
                "discounted": 1,
                "escalated": 1,
            },
            "divergence_source_distribution": {
                "known": {"Web Risk": 2},
                "unknown_count": 0,
            },
            "divergence_sanitizer_replacement_count": 0,
        }
    ]
