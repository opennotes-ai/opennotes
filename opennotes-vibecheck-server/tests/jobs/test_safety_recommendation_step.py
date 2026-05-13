"""Orchestrator wiring tests for image vision review pre-pass (TASK-1639.06)."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from src.analyses.safety._schemas import SafetyLevel, SafetyRecommendation
from src.analyses.safety.recommendation_agent import SafetyRecommendationInputs
from src.analyses.schemas import SectionSlug
from src.jobs import orchestrator
from tests.jobs.test_orchestrator_weather_stage import FakePool, _complete_sections


class SafetyConnection:
    def __init__(
        self,
        sections: dict[str, Any],
        *,
        url: str | None = "https://example.com/article",
        attempt_matches: bool = True,
        fail_execute: bool = False,
    ) -> None:
        self.sections = sections
        self.url = url
        self.attempt_matches = attempt_matches
        self.fail_execute = fail_execute
        self.written: dict[str, Any] | None = None

    async def fetchrow(
        self, query: str, _job_id: UUID, task_attempt: UUID
    ) -> dict[str, Any] | None:
        del query, task_attempt
        if not self.attempt_matches:
            return None
        return {"sections": self.sections, "url": self.url}

    async def execute(
        self,
        query: str,
        job_id: UUID,
        recommendation_json: str,
        task_attempt: UUID,
    ) -> str:
        if self.fail_execute:
            raise RuntimeError("safety column unavailable")
        self.written = {
            "query": query,
            "job_id": job_id,
            "recommendation_json": recommendation_json,
            "task_attempt": task_attempt,
        }
        return "UPDATE 1"


def _flagged_image_sections() -> dict[str, Any]:
    sections = _complete_sections()
    sections[SectionSlug.SAFETY_IMAGE_MODERATION.value] = {
        "state": "done",
        "attempt_id": str(uuid4()),
        "data": {
            "matches": [
                {
                    "utterance_id": "u1",
                    "image_url": "https://example.com/flagged.jpg",
                    "adult": 0.95,
                    "violence": 0.0,
                    "racy": 0.0,
                    "medical": 0.0,
                    "spoof": 0.0,
                    "flagged": True,
                    "max_likelihood": 0.95,
                }
            ]
        },
    }
    return sections


def _safe_recommendation() -> SafetyRecommendation:
    return SafetyRecommendation(
        level=SafetyLevel.SAFE,
        rationale="No concerning signals.",
        top_signals=[],
        unavailable_inputs=[],
    )


def _settings(*, flag_enabled: bool) -> Any:
    settings = MagicMock()
    settings.VIBECHECK_SAFETY_IMAGE_VISION_REVIEW_ENABLED = flag_enabled
    settings.MAX_IMAGES_MODERATED = 30
    return settings


@pytest.mark.asyncio
async def test_flag_disabled_does_not_pass_image_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_run(
        inputs: SafetyRecommendationInputs,
        settings: Any,
        *,
        image_urls: list[str] | None = None,
    ) -> SafetyRecommendation:
        del settings
        calls.append({"image_urls": image_urls, "inputs": inputs})
        return _safe_recommendation()

    monkeypatch.setattr(orchestrator, "run_safety_recommendation", fake_run)
    conn = SafetyConnection(_flagged_image_sections())

    await orchestrator._run_safety_recommendation_step(
        FakePool(conn),
        uuid4(),
        uuid4(),
        _settings(flag_enabled=False),
    )

    assert len(calls) == 1
    # Behavior identical to pre-flag state: either kwarg absent or None/[].
    assert not calls[0]["image_urls"]
    assert conn.written is not None


@pytest.mark.asyncio
async def test_flag_enabled_no_flagged_images_passes_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_run(
        inputs: SafetyRecommendationInputs,
        settings: Any,
        *,
        image_urls: list[str] | None = None,
    ) -> SafetyRecommendation:
        del settings, inputs
        calls.append({"image_urls": image_urls})
        return _safe_recommendation()

    monkeypatch.setattr(orchestrator, "run_safety_recommendation", fake_run)
    # Use the default _complete_sections which has zero image matches.
    conn = SafetyConnection(_complete_sections())

    await orchestrator._run_safety_recommendation_step(
        FakePool(conn),
        uuid4(),
        uuid4(),
        _settings(flag_enabled=True),
    )

    assert len(calls) == 1
    # No flagged images: either an explicit empty list or kwarg absent (None).
    assert not calls[0]["image_urls"]


@pytest.mark.asyncio
async def test_flag_enabled_passes_flagged_image_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_run(
        inputs: SafetyRecommendationInputs,
        settings: Any,
        *,
        image_urls: list[str] | None = None,
    ) -> SafetyRecommendation:
        del settings, inputs
        calls.append({"image_urls": image_urls})
        return _safe_recommendation()

    monkeypatch.setattr(orchestrator, "run_safety_recommendation", fake_run)
    conn = SafetyConnection(_flagged_image_sections())

    await orchestrator._run_safety_recommendation_step(
        FakePool(conn),
        uuid4(),
        uuid4(),
        _settings(flag_enabled=True),
    )

    assert len(calls) == 1
    assert calls[0]["image_urls"] == ["https://example.com/flagged.jpg"]


@pytest.mark.asyncio
async def test_flag_enabled_retries_without_images_on_vision_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_run(
        inputs: SafetyRecommendationInputs,
        settings: Any,
        *,
        image_urls: list[str] | None = None,
    ) -> SafetyRecommendation:
        del settings
        calls.append(
            {
                "image_urls": image_urls,
                "unavailable_inputs": list(inputs.unavailable_inputs),
            }
        )
        if image_urls:
            raise RuntimeError("vertex multimodal rejected image")
        return _safe_recommendation()

    monkeypatch.setattr(orchestrator, "run_safety_recommendation", fake_run)
    conn = SafetyConnection(_flagged_image_sections())

    await orchestrator._run_safety_recommendation_step(
        FakePool(conn),
        uuid4(),
        uuid4(),
        _settings(flag_enabled=True),
    )

    assert len(calls) == 2
    assert calls[0]["image_urls"] == ["https://example.com/flagged.jpg"]
    assert "image_vision_review" not in calls[0]["unavailable_inputs"]
    assert calls[1]["image_urls"] == []
    assert "image_vision_review" in calls[1]["unavailable_inputs"]
    assert conn.written is not None


@pytest.mark.asyncio
async def test_flag_disabled_does_not_retry_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_run(
        inputs: SafetyRecommendationInputs,
        settings: Any,
        *,
        image_urls: list[str] | None = None,
    ) -> SafetyRecommendation:
        del settings, inputs
        calls.append({"image_urls": image_urls})
        raise RuntimeError("non-vision failure")

    monkeypatch.setattr(orchestrator, "run_safety_recommendation", fake_run)
    conn = SafetyConnection(_flagged_image_sections())

    await orchestrator._run_safety_recommendation_step(
        FakePool(conn),
        uuid4(),
        uuid4(),
        _settings(flag_enabled=False),
    )

    # Flag disabled: only one call, outer except swallows and skips write.
    assert len(calls) == 1
    assert conn.written is None
