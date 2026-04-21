from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.analyses.opinions import subjective as subjective_module
from src.analyses.opinions._schemas import (
    _SubjectiveClaimLLM,
    _SubjectiveClaimsLLM,
)
from src.analyses.opinions.subjective import extract_subjective_claims
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


async def test_extract_subjective_claim_from_opinion_utterance(monkeypatch):
    scripted = _ScriptedAgent(
        {
            "The UI is ugly": _SubjectiveClaimsLLM(
                claims=[
                    _SubjectiveClaimLLM(
                        claim_text="The UI is ugly", stance="evaluates"
                    )
                ]
            ),
        }
    )
    monkeypatch.setattr(
        subjective_module, "build_agent", lambda *args, **kwargs: scripted
    )

    utterance = Utterance(utterance_id="u-op", kind="comment", text="The UI is ugly")
    claims = await extract_subjective_claims(utterance)

    assert len(claims) == 1
    assert claims[0].claim_text == "The UI is ugly"
    assert claims[0].utterance_id == "u-op"
    assert claims[0].stance == "evaluates"


async def test_extract_subjective_claims_excludes_factual_utterance(monkeypatch):
    scripted = _ScriptedAgent(
        {
            "The UI has 3 buttons": _SubjectiveClaimsLLM(claims=[]),
        }
    )
    monkeypatch.setattr(
        subjective_module, "build_agent", lambda *args, **kwargs: scripted
    )

    utterance = Utterance(
        utterance_id="u-fact", kind="comment", text="The UI has 3 buttons"
    )
    claims = await extract_subjective_claims(utterance)

    assert claims == []


async def test_extract_subjective_claims_uses_fallback_id_when_missing(monkeypatch):
    scripted = _ScriptedAgent(
        {
            "I like the new layout": _SubjectiveClaimsLLM(
                claims=[
                    _SubjectiveClaimLLM(
                        claim_text="I like the new layout", stance="supports"
                    )
                ]
            ),
        }
    )
    monkeypatch.setattr(
        subjective_module, "build_agent", lambda *args, **kwargs: scripted
    )

    utterance = Utterance(kind="post", text="I like the new layout")
    claims = await extract_subjective_claims(utterance, index=7)

    assert len(claims) == 1
    assert claims[0].utterance_id == "utt-7"
    assert claims[0].stance == "supports"


async def test_extract_subjective_claims_preserves_stance_values(monkeypatch):
    scripted = _ScriptedAgent(
        {
            "multi-stance utterance": _SubjectiveClaimsLLM(
                claims=[
                    _SubjectiveClaimLLM(
                        claim_text="this change is bad", stance="opposes"
                    ),
                    _SubjectiveClaimLLM(
                        claim_text="the old flow is better", stance="supports"
                    ),
                ]
            ),
        }
    )
    monkeypatch.setattr(
        subjective_module, "build_agent", lambda *args, **kwargs: scripted
    )

    utterance = Utterance(
        utterance_id="u-mix", kind="comment", text="multi-stance utterance"
    )
    claims = await extract_subjective_claims(utterance)

    stances = {c.stance for c in claims}
    assert stances == {"opposes", "supports"}
    assert all(c.utterance_id == "u-mix" for c in claims)
