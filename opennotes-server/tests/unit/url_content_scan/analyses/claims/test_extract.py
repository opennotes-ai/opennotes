from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.url_content_scan.utterances.schema import Utterance


@pytest.mark.asyncio
async def test_extract_claims_returns_structured_claims_from_default_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.url_content_scan.analyses.claims.extract import (
        ExtractedClaim,
        _ClaimExtractionResponse,
        extract_claims,
    )

    utterance = Utterance(
        utterance_id="u-1",
        kind="comment",
        text="The city approved the tax increase yesterday.",
    )

    async def fake_run(prompt: str, **kwargs: object) -> SimpleNamespace:
        assert "The city approved the tax increase yesterday." in prompt
        assert kwargs["model"] is not None
        return SimpleNamespace(
            output=_ClaimExtractionResponse(
                claims=[
                    ExtractedClaim(
                        claim_text="The city approved the tax increase yesterday.",
                        confidence=0.91,
                    )
                ]
            )
        )

    monkeypatch.setattr(
        "src.url_content_scan.analyses.claims.extract._CLAIM_EXTRACTION_AGENT.run",
        fake_run,
    )

    claims = await extract_claims(utterance)

    assert claims == [
        ExtractedClaim(
            claim_text="The city approved the tax increase yesterday.",
            confidence=0.91,
        )
    ]


@pytest.mark.asyncio
async def test_extract_claims_skips_blank_utterances_without_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.url_content_scan.analyses.claims.extract import extract_claims

    async def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        raise AssertionError("agent.run should not execute for blank utterances")

    monkeypatch.setattr(
        "src.url_content_scan.analyses.claims.extract._CLAIM_EXTRACTION_AGENT.run",
        fake_run,
    )

    claims = await extract_claims(Utterance(utterance_id="u-1", kind="comment", text="   "))

    assert claims == []
