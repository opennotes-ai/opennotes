from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.url_content_scan.utterances.schema import Utterance


@pytest.mark.asyncio
async def test_run_subjective_uses_default_extractor_when_not_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.url_content_scan.analyses.opinions.subjective import (
        _SubjectiveClaimOutput,
        _SubjectiveExtractionResponse,
        run_subjective,
    )

    utterances = [
        Utterance(utterance_id="u-1", kind="post", text="This redesign is excellent."),
        Utterance(utterance_id="u-2", kind="comment", text="The API shipped yesterday."),
    ]

    async def fake_run(prompt: str, **kwargs: object) -> SimpleNamespace:
        assert kwargs["model"] is not None
        by_prompt = {
            "This redesign is excellent.": _SubjectiveExtractionResponse(
                claims=[
                    _SubjectiveClaimOutput(
                        claim_text="This redesign is excellent.",
                        stance="evaluates",
                    )
                ]
            ),
            "The API shipped yesterday.": _SubjectiveExtractionResponse(claims=[]),
        }
        return SimpleNamespace(output=by_prompt[prompt])

    monkeypatch.setattr(
        "src.url_content_scan.analyses.opinions.subjective._SUBJECTIVE_AGENT.run",
        fake_run,
    )

    report = await run_subjective(utterances)

    assert [claim.claim_text for claim in report.subjective_claims] == [
        "This redesign is excellent."
    ]
    assert report.subjective_claims[0].utterance_id == "u-1"
    assert report.subjective_claims[0].stance == "evaluates"
