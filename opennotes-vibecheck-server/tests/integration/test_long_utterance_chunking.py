"""Long-utterance chunking contract across text analyses (TASK-1619.08)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.analyses.claims import extract as claims_extract
from src.analyses.claims._claims_schemas import (
    BulkClaimExtractionResponse,
    ClaimCategory,
)
from src.analyses.claims.extract import extract_claims_bulk
from src.analyses.opinions import subjective as subjective_extract
from src.analyses.opinions._schemas import _BulkSubjectiveClaimsLLM
from src.analyses.opinions.subjective import extract_subjective_claims_bulk
from src.analyses.safety.gcp_moderation import moderate_texts_gcp
from src.analyses.safety.moderation import check_content_moderation_bulk
from src.config import Settings
from src.services.openai_moderation import ModerationResult
from src.utterances.schema import Utterance


@dataclass
class _FakeRunResult:
    output: Any


def _long_post() -> str:
    return "This policy is harmful and unfair. " * 500


def _utterance() -> Utterance:
    return Utterance(
        utterance_id="post-0-deadbeef",
        kind="post",
        text=_long_post(),
        author="alice",
    )


def _openai_result(flagged: bool, score: float) -> ModerationResult:
    return ModerationResult(
        flagged=flagged,
        categories={"harassment": flagged},
        scores={"harassment": score},
        max_score=score,
        flagged_categories=["harassment"] if flagged else [],
    )


async def test_long_utterance_chunking_flows_through_text_analyses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utterance = _utterance()
    settings = Settings()

    openai_service = AsyncMock()

    def openai_responses(texts: list[str]) -> list[ModerationResult]:
        assert len(texts) > 1
        assert utterance.text not in texts
        return [
            _openai_result(flagged=index == 0, score=0.96 if index == 0 else 0.01)
            for index, _text in enumerate(texts)
        ]

    openai_service.moderate_texts = AsyncMock(side_effect=openai_responses)
    openai_matches = await check_content_moderation_bulk([utterance], openai_service)

    assert any(match.chunk_idx == 0 for match in openai_matches)
    aggregate = next(match for match in openai_matches if match.chunk_idx is None)
    assert aggregate.chunk_count is not None
    assert aggregate.chunk_count > 1
    assert aggregate.utterance_text == utterance.text

    gcp_requests: list[str] = []

    def gcp_handler(request: httpx.Request) -> httpx.Response:
        import json

        content = json.loads(request.content.decode())["document"]["content"]
        gcp_requests.append(content)
        confidence = 0.93 if len(gcp_requests) == 1 else 0.01
        return httpx.Response(
            200,
            json={"moderationCategories": [{"name": "Toxic", "confidence": confidence}]},
        )

    transport = httpx.MockTransport(gcp_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch(
            "src.analyses.safety.gcp_moderation.get_access_token",
            return_value="token",
        ):
            gcp_matches = await moderate_texts_gcp(
                [utterance],
                httpx_client=client,
                settings=settings,
                threshold=0.5,
            )

    assert len(gcp_requests) > 1
    assert any(match.chunk_idx == 0 for match in gcp_matches)
    assert any(match.chunk_idx is None for match in gcp_matches)

    async def fake_subjective_run(_agent: object, user_prompt: str) -> _FakeRunResult:
        assert utterance.text not in user_prompt
        return _FakeRunResult(
            _BulkSubjectiveClaimsLLM.model_validate(
                {
                    "results": [
                        {
                            "utterance_index": 0,
                            "claims": [
                                {
                                    "claim_text": "The policy is unfair.",
                                    "stance": "opposes",
                                }
                            ],
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(subjective_extract, "build_agent", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        subjective_extract,
        "run_vertex_agent_with_retry",
        fake_subjective_run,
    )
    subjective_claims = await extract_subjective_claims_bulk([utterance], settings=settings)

    subjective_claim = subjective_claims[0][0]
    assert subjective_claim.chunk_idx == 0
    assert subjective_claim.chunk_count == aggregate.chunk_count

    async def fake_claims_run(_agent: object, user_prompt: str) -> _FakeRunResult:
        assert utterance.text not in user_prompt
        return _FakeRunResult(
            BulkClaimExtractionResponse.model_validate(
                {
                    "results": [
                        {
                            "utterance_index": 0,
                            "claims": [
                                {
                                    "claim_text": "The policy is harmful.",
                                    "category": ClaimCategory.PREDICTIONS,
                                    "confidence": 0.9,
                                }
                            ],
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(claims_extract, "build_agent", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        claims_extract,
        "run_vertex_agent_with_retry",
        fake_claims_run,
    )
    claims = await extract_claims_bulk([utterance], settings)

    claim = claims[0][0]
    assert claim.chunk_idx == 0
    assert claim.chunk_count == aggregate.chunk_count
