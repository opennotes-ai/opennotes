from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.analyses.opinions import subjective as subjective_module
from src.analyses.opinions._schemas import (
    _BulkSubjectiveClaimsLLM,
    _SubjectiveClaimLLM,
    _SubjectiveClaimsLLM,
)
from src.analyses.opinions.subjective import (
    extract_subjective_claims,
    extract_subjective_claims_bulk,
)
from src.config import Settings
from src.utterances.schema import Utterance


@dataclass
class _FakeRunResult:
    output: Any


class _ScriptedAgent:
    def __init__(self, response_by_text: dict[str, _SubjectiveClaimsLLM]) -> None:
        self._by_text = response_by_text
        self.calls: list[str] = []

    async def run(self, prompt: str) -> _FakeRunResult:
        self.calls.append(prompt)
        for needle, payload in self._by_text.items():
            if needle in prompt:
                return _FakeRunResult(output=payload)
        return _FakeRunResult(output=_SubjectiveClaimsLLM(claims=[]))


@pytest.mark.xfail(
    reason="tests deprecated single-utterance wrapper path; bulk coverage TBD", strict=False
)
async def test_extract_subjective_claim_from_opinion_utterance(monkeypatch):
    scripted = _ScriptedAgent(
        {
            "The UI is ugly": _SubjectiveClaimsLLM(
                claims=[_SubjectiveClaimLLM(claim_text="The UI is ugly", stance="evaluates")]
            ),
        }
    )
    monkeypatch.setattr(subjective_module, "build_agent", lambda *args, **kwargs: scripted)

    utterance = Utterance(utterance_id="u-op", kind="comment", text="The UI is ugly")
    claims = await extract_subjective_claims(utterance)

    assert len(claims) == 1
    assert claims[0].claim_text == "The UI is ugly"
    assert claims[0].utterance_id == "u-op"
    assert claims[0].stance == "evaluates"


@pytest.mark.xfail(
    reason="tests deprecated single-utterance wrapper path; bulk coverage TBD", strict=False
)
async def test_extract_subjective_claims_excludes_factual_utterance(monkeypatch):
    scripted = _ScriptedAgent(
        {
            "The UI has 3 buttons": _SubjectiveClaimsLLM(claims=[]),
        }
    )
    monkeypatch.setattr(subjective_module, "build_agent", lambda *args, **kwargs: scripted)

    utterance = Utterance(utterance_id="u-fact", kind="comment", text="The UI has 3 buttons")
    claims = await extract_subjective_claims(utterance)

    assert claims == []


@pytest.mark.xfail(
    reason="tests deprecated single-utterance wrapper path; bulk coverage TBD", strict=False
)
async def test_extract_subjective_claims_uses_fallback_id_when_missing(monkeypatch):
    scripted = _ScriptedAgent(
        {
            "I like the new layout": _SubjectiveClaimsLLM(
                claims=[_SubjectiveClaimLLM(claim_text="I like the new layout", stance="supports")]
            ),
        }
    )
    monkeypatch.setattr(subjective_module, "build_agent", lambda *args, **kwargs: scripted)

    utterance = Utterance(kind="post", text="I like the new layout")
    claims = await extract_subjective_claims(utterance, index=7)

    assert len(claims) == 1
    assert claims[0].utterance_id == "utt-7"
    assert claims[0].stance == "supports"


@pytest.mark.xfail(
    reason="tests deprecated single-utterance wrapper path; bulk coverage TBD", strict=False
)
async def test_extract_subjective_claims_preserves_stance_values(monkeypatch):
    scripted = _ScriptedAgent(
        {
            "multi-stance utterance": _SubjectiveClaimsLLM(
                claims=[
                    _SubjectiveClaimLLM(claim_text="this change is bad", stance="opposes"),
                    _SubjectiveClaimLLM(claim_text="the old flow is better", stance="supports"),
                ]
            ),
        }
    )
    monkeypatch.setattr(subjective_module, "build_agent", lambda *args, **kwargs: scripted)

    utterance = Utterance(utterance_id="u-mix", kind="comment", text="multi-stance utterance")
    claims = await extract_subjective_claims(utterance)

    stances = {c.stance for c in claims}
    assert stances == {"opposes", "supports"}
    assert all(c.utterance_id == "u-mix" for c in claims)


async def test_extract_subjective_claims_bulk_preserves_chunk_refs(monkeypatch):
    long_text = "This experience is frustrating and unfair. " * 500

    async def fake_run_vertex_agent_with_retry(_agent, user_prompt: str):
        assert "[0]" in user_prompt
        assert long_text not in user_prompt
        return _FakeRunResult(
            output=_BulkSubjectiveClaimsLLM.model_validate(
                {
                    "results": [
                        {
                            "utterance_index": 0,
                            "claims": [
                                {
                                    "claim_text": "The experience is unfair.",
                                    "stance": "opposes",
                                }
                            ],
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(subjective_module, "build_agent", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        subjective_module,
        "run_vertex_agent_with_retry",
        fake_run_vertex_agent_with_retry,
    )

    claims_by_utterance = await extract_subjective_claims_bulk(
        [
            Utterance(
                utterance_id="comment-1",
                kind="comment",
                text=long_text,
                author="alice",
            )
        ],
        settings=Settings(),
    )

    claim = claims_by_utterance[0][0]
    assert claim.utterance_id == "comment-1"
    assert claim.chunk_idx == 0
    assert claim.chunk_count is not None
    assert claim.chunk_count > 1


async def test_extract_subjective_claims_bulk_returns_one_entry_per_chunk(monkeypatch):
    long_text = "This experience is frustrating and unfair. " * 500

    def fake_build_agent(_settings, *, output_type=None, system_prompt=None, name=None):
        assert output_type is _BulkSubjectiveClaimsLLM
        assert system_prompt is not None
        assert "numbered list of text segments" in system_prompt.lower()
        assert "bracketed input index" in system_prompt.lower()
        return object()

    async def fake_run_vertex_agent_with_retry(_agent, user_prompt: str):
        prompt_lines = [line for line in user_prompt.splitlines() if line.startswith("[")]
        assert len(prompt_lines) > 1
        return _FakeRunResult(
            output=_BulkSubjectiveClaimsLLM.model_validate(
                {
                    "results": [
                        {
                            "utterance_index": index,
                            "claims": [
                                {
                                    "claim_text": f"Chunk {index} is unfair.",
                                    "stance": "opposes",
                                }
                            ],
                        }
                        for index, _line in enumerate(prompt_lines)
                    ]
                }
            )
        )

    monkeypatch.setattr(subjective_module, "build_agent", fake_build_agent)
    monkeypatch.setattr(
        subjective_module,
        "run_vertex_agent_with_retry",
        fake_run_vertex_agent_with_retry,
    )

    claims_by_utterance = await extract_subjective_claims_bulk(
        [
            Utterance(
                utterance_id="comment-1",
                kind="comment",
                text=long_text,
                author="alice",
            )
        ],
        settings=Settings(),
    )

    claims = claims_by_utterance[0]
    assert len(claims) > 1
    assert [claim.chunk_idx for claim in claims] == list(range(len(claims)))
    assert {claim.chunk_count for claim in claims} == {len(claims)}
