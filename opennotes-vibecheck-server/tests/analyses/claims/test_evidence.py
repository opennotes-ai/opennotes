"""Tests for claim evidence enrichment (`evidence.py` and `evidence_slot.py`)."""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.analyses.claims import evidence
from src.analyses.claims._claims_schemas import (
    ClaimCategory,
    ClaimsReport,
    DedupedClaim,
    SourceKind,
)
from src.analyses.claims.evidence_slot import run_claims_evidence
from src.config import Settings


class _Acquire:
    def __init__(self, row: Any) -> None:
        self._row = row

    async def __aenter__(self) -> _Conn:
        return _Conn(self._row)

    async def __aexit__(self, *args: object) -> None:
        return None


class _Conn:
    def __init__(self, row: Any) -> None:
        self._row = row

    async def fetchval(self, *_args: object) -> Any:
        return self._row


class _Pool:
    def __init__(self, row: Any) -> None:
        self._row = row

    def acquire(self) -> _Acquire:
        return _Acquire(self._row)


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def no_external_settings() -> Settings:
    return Settings(EVIDENCE_MAX_EXTERNAL_CLAIMS=0)


def _claims_report(*texts: str) -> ClaimsReport:
    return ClaimsReport(
        deduped_claims=[
            DedupedClaim(
                canonical_text=text,
                category=ClaimCategory.POTENTIALLY_FACTUAL,
                occurrence_count=1,
                author_count=1,
                utterance_ids=["u-1"],
                representative_authors=["alice"],
            )
            for text in texts
        ],
        total_claims=len(texts),
        total_unique=len(texts),
    )


def _deduped_claim_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "canonical_text": "The moon is round.",
        "category": ClaimCategory.POTENTIALLY_FACTUAL,
        "occurrence_count": 1,
        "author_count": 1,
        "utterance_ids": ["u-1"],
        "representative_authors": ["alice"],
    }
    payload.update(overrides)
    return payload


class _Payload:
    def __init__(self, claims_report: ClaimsReport) -> None:
        self.claims_report = claims_report


class _AgentCall:
    def __init__(
        self,
        *,
        name: str,
        tier: str,
        output_type: type[Any],
        builtin_tools: list[Any],
    ) -> None:
        self.name = name
        self.tier = tier
        self.output_type = output_type
        self.builtin_tools = builtin_tools


class _Returned:
    def __init__(self, content: list[dict[str, str]]) -> None:
        self.content = content


class _Response:
    def __init__(self, urls: list[str]) -> None:
        self.builtin_tool_calls = [(object(), _Returned([{"uri": url} for url in urls]))]


class _RunResult:
    def __init__(self, output: Any, urls: list[str] | None = None) -> None:
        self.output = output
        self.response = _Response(urls or [])


async def _no_external_fetcher(
    claim_texts: list[str], _settings: Settings
) -> dict[str, list[dict[str, Any]]]:
    return {text: [] for text in claim_texts}


async def _external_facts_for_claims(
    claim_texts: list[str],
    expected_claim: str,
    statement: str,
    source_ref: str,
) -> dict[str, list[dict[str, Any]]]:
    return {
        text: [
            {
                "statement": statement,
                "source_kind": SourceKind.EXTERNAL.value,
                "source_ref": source_ref,
            }
        ]
        if text == expected_claim
        else []
        for text in claim_texts
    }


def test_deduped_claim_defaults_facts_to_verify_to_zero() -> None:
    claim = DedupedClaim(**_deduped_claim_payload())

    assert claim.facts_to_verify == 0


def test_deduped_claim_round_trips_positive_facts_to_verify() -> None:
    claim = DedupedClaim(**_deduped_claim_payload(facts_to_verify=3))

    dumped = claim.model_dump(mode="json")

    assert dumped["facts_to_verify"] == 3
    assert DedupedClaim.model_validate(dumped).facts_to_verify == 3


def test_deduped_claim_rejects_negative_facts_to_verify() -> None:
    with pytest.raises(ValidationError):
        DedupedClaim(**_deduped_claim_payload(facts_to_verify=-1))


def test_evidence_settings_default_external_claim_and_candidate_caps() -> None:
    settings = Settings()

    assert settings.EVIDENCE_MAX_EXTERNAL_CLAIMS == 10
    assert settings.EVIDENCE_SYNTHESIS_CANDIDATE_CAP == 60


def test_proportional_shrink_caps_counts_with_non_zero_floor() -> None:
    allotments = evidence.proportional_shrink([8, 3, 1], 10)

    assert sum(allotments) <= 10
    assert all(allotment >= 1 for allotment in allotments)
    assert allotments[0] >= allotments[1] >= allotments[2]


def test_proportional_shrink_preserves_zero_entries_and_identity_when_under_cap() -> None:
    assert evidence.proportional_shrink([2, 0, 3], 10) == [2, 0, 3]
    assert evidence.proportional_shrink([8, 0, 3], 5)[1] == 0


def test_external_evidence_candidate_carries_pipeline_fields() -> None:
    candidate = evidence._ExternalEvidenceCandidate(
        canonical_text="The moon is round.",
        statement="NASA describes the moon as round.",
        source_ref="https://science.example/moon",
    )

    assert candidate.model_dump() == {
        "canonical_text": "The moon is round.",
        "statement": "NASA describes the moon as round.",
        "source_ref": "https://science.example/moon",
    }


@pytest.mark.asyncio
async def test_build_supporting_facts_only_includes_potentially_factual_claims(
    settings: Settings,
) -> None:
    claims = [
        DedupedClaim(
            canonical_text="The moon is round.",
            category=ClaimCategory.POTENTIALLY_FACTUAL,
            occurrence_count=1,
            author_count=1,
            utterance_ids=["u-1"],
            representative_authors=["alice"],
        ),
        DedupedClaim(
            canonical_text="I think it will rain.",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=1,
            author_count=1,
            utterance_ids=["u-2"],
            representative_authors=["alice"],
        ),
    ]

    facts = await evidence.build_supporting_facts_by_claim(
        claims,
        settings,
        external_fetcher=lambda claim_texts, _settings: _external_facts_for_claims(
            claim_texts,
            "The moon is round.",
            "NASA describes the Moon as approximately spherical.",
            "https://science.example/moon",
        ),
    )

    assert [fact.model_dump(mode="json") for fact in facts["The moon is round."]] == [
        {
            "statement": "NASA describes the Moon as approximately spherical.",
            "source_kind": SourceKind.EXTERNAL.value,
            "source_ref": "https://science.example/moon",
        }
    ]
    assert "I think it will rain." not in facts


@pytest.mark.asyncio
async def test_build_supporting_facts_budgets_external_batch(
    settings: Settings,
) -> None:
    calls: list[list[str]] = []

    async def fake_external_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        calls.append(list(claim_texts))
        return {text: [] for text in claim_texts}

    claims = [
        DedupedClaim(
            canonical_text=f"claim {index}",
            category=ClaimCategory.POTENTIALLY_FACTUAL,
            occurrence_count=1,
            author_count=1,
            utterance_ids=[],
            representative_authors=["alice"],
        )
        for index in range(6)
    ]

    await evidence.build_supporting_facts_by_claim(
        claims,
        settings,
        external_fetcher=fake_external_fetcher,
    )

    assert calls == [[f"claim {i}" for i in range(6)]]


@pytest.mark.asyncio
async def test_build_supporting_facts_adds_external_facts(
    settings: Settings,
) -> None:
    async def fake_external_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            claim_texts[0]: [
                {
                    "statement": "NASA describes the moon as round.",
                    "source_kind": SourceKind.EXTERNAL.value,
                    "source_ref": "https://science.example/moon",
                }
            ]
        }

    facts = await evidence.build_supporting_facts_by_claim(
        _claims_report("The moon is round.").deduped_claims,
        settings,
        external_fetcher=fake_external_fetcher,
    )

    assert [fact.source_kind for fact in facts["The moon is round."]] == [SourceKind.EXTERNAL]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "utterance_text",
    [
        "The moon is round.",
        "  the   moon is ROUND  ",
        "The moon is round!!!",
        "Claim: The moon is round.",
    ],
)
async def test_build_supporting_facts_filters_external_tautologies(
    settings: Settings,
    utterance_text: str,
) -> None:
    async def fake_external_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            claim_texts[0]: [
                {
                    "statement": utterance_text,
                    "source_kind": SourceKind.EXTERNAL.value,
                    "source_ref": "https://science.example/moon",
                }
            ]
        }

    facts = await evidence.build_supporting_facts_by_claim(
        _claims_report("The moon is round.").deduped_claims,
        settings,
        external_fetcher=fake_external_fetcher,
    )

    assert facts == {}


@pytest.mark.asyncio
async def test_build_supporting_facts_keeps_external_statements_with_context(
    settings: Settings,
) -> None:
    async def fake_external_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            claim_texts[0]: [
                {
                    "statement": (
                        "Hydrostatic equilibrium pulls large rocky bodies into round shapes."
                    ),
                    "source_kind": SourceKind.EXTERNAL.value,
                    "source_ref": "https://science.example/moon",
                }
            ]
        }

    facts = await evidence.build_supporting_facts_by_claim(
        _claims_report("The moon is round.").deduped_claims,
        settings,
        external_fetcher=fake_external_fetcher,
    )

    assert [fact.model_dump(mode="json") for fact in facts["The moon is round."]] == [
        {
            "statement": "Hydrostatic equilibrium pulls large rocky bodies into round shapes.",
            "source_kind": SourceKind.EXTERNAL.value,
            "source_ref": "https://science.example/moon",
        }
    ]


@pytest.mark.asyncio
async def test_build_supporting_facts_keeps_non_tautological_external_facts(
    settings: Settings,
) -> None:
    async def fake_external_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            claim_texts[0]: [
                {
                    "statement": "NASA describes the Moon as approximately spherical.",
                    "source_kind": SourceKind.EXTERNAL.value,
                    "source_ref": "https://science.example/moon-shape",
                }
            ]
        }

    facts = await evidence.build_supporting_facts_by_claim(
        _claims_report("The moon is round.").deduped_claims,
        settings,
        external_fetcher=fake_external_fetcher,
    )

    assert [fact.model_dump(mode="json") for fact in facts["The moon is round."]] == [
        {
            "statement": "NASA describes the Moon as approximately spherical.",
            "source_kind": SourceKind.EXTERNAL.value,
            "source_ref": "https://science.example/moon-shape",
        }
    ]


def test_grounded_urls_from_result_normalizes_search_result_urls() -> None:
    class _SearchReturned:
        content: ClassVar[list[dict[str, str]]] = [
            {"uri": "HTTPS://Example.Test/source/"},
            {"uri": "https://example.test/source?ref=search"},
        ]

    class _SearchResponse:
        builtin_tool_calls: ClassVar[list[tuple[object, _SearchReturned]]] = [
            (object(), _SearchReturned())
        ]

    class _Result:
        response = _SearchResponse()

    assert evidence._grounded_urls_from_result(_Result()) == {
        "https://example.test/source",
        "https://example.test/source?ref=search",
    }


@pytest.mark.asyncio
async def test_cluster_claims_shortcuts_empty_and_single_claim(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    def fail_build_agent(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("single-claim clustering should not call the agent")

    monkeypatch.setattr(evidence, "build_agent", fail_build_agent)

    assert await evidence._cluster_claims_for_grounding([], settings) == []
    assert await evidence._cluster_claims_for_grounding(["The moon is round."], settings) == [
        ["The moon is round."]
    ]


@pytest.mark.asyncio
async def test_cluster_claims_repairs_dropped_and_duplicated_claims(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    def fake_build_agent(
        _settings: Settings,
        *,
        output_type: type[Any],
        system_prompt: str | None = None,
        name: str | None = None,
        tier: str = "fast",
        builtin_tools: list[Any] | tuple[Any, ...] = (),
        **_kwargs: object,
    ) -> _AgentCall:
        del system_prompt
        return _AgentCall(
            name=name or "",
            tier=tier,
            output_type=output_type,
            builtin_tools=list(builtin_tools),
        )

    async def fake_run(_agent: _AgentCall, _prompt: str) -> _RunResult:
        return _RunResult(
            evidence._ClusterResponse(
                groups=[
                    evidence._ClaimGroup(claim_texts=["claim one", "claim one"]),
                    evidence._ClaimGroup(claim_texts=["claim two"]),
                ]
            )
        )

    monkeypatch.setattr(evidence, "build_agent", fake_build_agent)
    monkeypatch.setattr(evidence, "run_vertex_agent_with_retry", fake_run)

    groups = await evidence._cluster_claims_for_grounding(
        ["claim one", "claim two", "claim three"],
        settings,
    )

    assert groups == [["claim one"], ["claim two"], ["claim three"]]


@pytest.mark.asyncio
async def test_fetch_grounded_candidates_keeps_successes_and_logs_drops(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    calls: list[_AgentCall] = []
    telemetry: list[tuple[str, dict[str, object]]] = []

    def fake_build_agent(
        _settings: Settings,
        *,
        output_type: type[Any],
        system_prompt: str | None = None,
        name: str | None = None,
        tier: str = "fast",
        builtin_tools: list[Any] | tuple[Any, ...] = (),
        **_kwargs: object,
    ) -> _AgentCall:
        del system_prompt, output_type
        call = _AgentCall(
            name=name or "",
            tier=tier,
            output_type=evidence._ExternalEvidenceResponse,
            builtin_tools=list(builtin_tools),
        )
        calls.append(call)
        return call

    async def fake_run(_agent: _AgentCall, prompt: str) -> _RunResult:
        if "bad group" in prompt:
            raise RuntimeError("one group failed")
        return _RunResult(
            evidence._ExternalEvidenceResponse(
                facts=[
                    evidence._ExternalEvidenceItem(
                        canonical_text="claim one",
                        statement="Supported fact.",
                        source_ref="https://example.test/source",
                    ),
                    evidence._ExternalEvidenceItem(
                        canonical_text="claim one",
                        statement="Dropped fact.",
                        source_ref="https://example.test/missing",
                    ),
                ]
            ),
            urls=["https://example.test/source/"],
        )

    def fake_logfire_info(event_name: str, **kwargs: object) -> None:
        if event_name.startswith("vibecheck.evidence.grounded_"):
            telemetry.append((event_name, kwargs))

    monkeypatch.setattr(evidence, "build_agent", fake_build_agent)
    monkeypatch.setattr(evidence, "run_vertex_agent_with_retry", fake_run)
    monkeypatch.setattr(evidence.logfire, "info", fake_logfire_info)

    candidates = await evidence._fetch_grounded_candidates_for_groups(
        [["claim one"], ["bad group"]],
        settings,
    )

    assert [candidate.model_dump() for candidate in candidates] == [
        {
            "canonical_text": "claim one",
            "statement": "Supported fact.",
            "source_ref": "https://example.test/source",
        }
    ]
    assert [(call.name, call.tier) for call in calls] == [
        ("vibecheck.claims_evidence_fetch", "fast"),
        ("vibecheck.claims_evidence_fetch", "fast"),
    ]
    assert telemetry == [
        (
            "vibecheck.evidence.grounded_url_filter_drop",
            {
                "claim_text": "claim one",
                "source_ref": "https://example.test/missing",
                "reason": "not_in_grounded_metadata",
            },
        ),
        (
            "vibecheck.evidence.grounded_fetch_failed",
            {"group_size": 1, "error_type": "RuntimeError"},
        ),
        (
            "vibecheck.evidence.grounded_fetch_summary",
            {"groups_total": 2, "groups_failed": 1},
        ),
    ]


@pytest.mark.asyncio
async def test_dedupe_and_sanity_check_candidates_returns_subset(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    def fake_build_agent(
        _settings: Settings,
        *,
        output_type: type[Any],
        system_prompt: str | None = None,
        name: str | None = None,
        tier: str = "fast",
        builtin_tools: list[Any] | tuple[Any, ...] = (),
        **_kwargs: object,
    ) -> _AgentCall:
        del system_prompt
        return _AgentCall(
            name=name or "",
            tier=tier,
            output_type=output_type,
            builtin_tools=list(builtin_tools),
        )

    async def fake_run(_agent: _AgentCall, _prompt: str) -> _RunResult:
        return _RunResult(
            evidence._SanityResponse(
                candidates=[
                    evidence._ExternalEvidenceCandidate(
                        canonical_text="claim one",
                        statement="Supported fact.",
                        source_ref="https://example.test/source/",
                    ),
                    evidence._ExternalEvidenceCandidate(
                        canonical_text="hallucinated claim",
                        statement="Not allowed.",
                        source_ref="https://example.test/other",
                    ),
                ]
            )
        )

    monkeypatch.setattr(evidence, "build_agent", fake_build_agent)
    monkeypatch.setattr(evidence, "run_vertex_agent_with_retry", fake_run)

    candidates = [
        evidence._ExternalEvidenceCandidate(
            canonical_text="claim one",
            statement="Supported fact.",
            source_ref="https://example.test/source",
        ),
        evidence._ExternalEvidenceCandidate(
            canonical_text="claim one",
            statement="Supported fact.",
            source_ref="https://example.test/source/",
        ),
        evidence._ExternalEvidenceCandidate(
            canonical_text="claim two",
            statement="Off topic.",
            source_ref="https://example.test/off-topic",
        ),
    ]

    clean = await evidence._dedupe_and_sanity_check_candidates(candidates, settings)

    assert [candidate.model_dump() for candidate in clean] == [
        {
            "canonical_text": "claim one",
            "statement": "Supported fact.",
            "source_ref": "https://example.test/source/",
        }
    ]


@pytest.mark.asyncio
async def test_dedupe_and_sanity_check_candidates_caps_prompt_and_logs_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []
    telemetry: list[tuple[str, dict[str, object]]] = []

    def fake_build_agent(
        _settings: Settings,
        *,
        output_type: type[Any],
        system_prompt: str | None = None,
        name: str | None = None,
        tier: str = "fast",
        builtin_tools: list[Any] | tuple[Any, ...] = (),
        **_kwargs: object,
    ) -> _AgentCall:
        del system_prompt
        return _AgentCall(
            name=name or "",
            tier=tier,
            output_type=output_type,
            builtin_tools=list(builtin_tools),
        )

    async def fake_run(_agent: _AgentCall, prompt: str) -> _RunResult:
        prompts.append(prompt)
        return _RunResult(evidence._SanityResponse(candidates=[]))

    def fake_logfire_info(event_name: str, **kwargs: object) -> None:
        telemetry.append((event_name, kwargs))

    monkeypatch.setattr(evidence, "build_agent", fake_build_agent)
    monkeypatch.setattr(evidence, "run_vertex_agent_with_retry", fake_run)
    monkeypatch.setattr(evidence.logfire, "info", fake_logfire_info)

    candidates = [
        evidence._ExternalEvidenceCandidate(
            canonical_text=f"claim {claim_index}",
            statement=f"candidate {claim_index}-{candidate_index}",
            source_ref=f"https://example.test/{claim_index}/{candidate_index}",
        )
        for claim_index in range(3)
        for candidate_index in range(10)
    ]

    clean = await evidence._dedupe_and_sanity_check_candidates(
        candidates,
        Settings(EVIDENCE_SYNTHESIS_CANDIDATE_CAP=5),
    )

    assert clean == []
    assert len(prompts) == 1
    assert prompts[0].count("canonical_text:") == 5
    assert telemetry == [
        (
            "vibecheck.evidence.sanity_prompt_length",
            {"prompt_length": len(prompts[0])},
        )
    ]


@pytest.mark.asyncio
async def test_dedupe_and_sanity_check_candidates_keeps_unique_candidates_when_sanity_fails(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    telemetry: list[tuple[str, dict[str, object]]] = []

    def fake_build_agent(
        _settings: Settings,
        *,
        output_type: type[Any],
        system_prompt: str | None = None,
        name: str | None = None,
        tier: str = "fast",
        builtin_tools: list[Any] | tuple[Any, ...] = (),
        **_kwargs: object,
    ) -> _AgentCall:
        del system_prompt
        return _AgentCall(
            name=name or "",
            tier=tier,
            output_type=output_type,
            builtin_tools=list(builtin_tools),
        )

    async def fake_run(_agent: _AgentCall, _prompt: str) -> _RunResult:
        raise ValueError("sanity model unavailable")

    def fake_logfire_info(event_name: str, **kwargs: object) -> None:
        telemetry.append((event_name, kwargs))

    monkeypatch.setattr(evidence, "build_agent", fake_build_agent)
    monkeypatch.setattr(evidence, "run_vertex_agent_with_retry", fake_run)
    monkeypatch.setattr(evidence.logfire, "info", fake_logfire_info)

    candidates = [
        evidence._ExternalEvidenceCandidate(
            canonical_text="claim one",
            statement="Supported fact.",
            source_ref="https://example.test/source",
        ),
        evidence._ExternalEvidenceCandidate(
            canonical_text="claim one",
            statement="Supported fact.",
            source_ref="https://example.test/source/",
        ),
        evidence._ExternalEvidenceCandidate(
            canonical_text="claim two",
            statement="Another fact.",
            source_ref="https://example.test/other",
        ),
    ]

    clean = await evidence._dedupe_and_sanity_check_candidates(candidates, settings)

    assert [candidate.model_dump() for candidate in clean] == [
        {
            "canonical_text": "claim one",
            "statement": "Supported fact.",
            "source_ref": "https://example.test/source",
        },
        {
            "canonical_text": "claim two",
            "statement": "Another fact.",
            "source_ref": "https://example.test/other",
        },
    ]
    assert [event for event in telemetry if event[0] == "vibecheck.evidence.sanity_failed"] == [
        ("vibecheck.evidence.sanity_failed", {"error_type": "ValueError"})
    ]


@pytest.mark.asyncio
async def test_curate_supporting_facts_uses_one_synthesis_call_and_external_kind(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    calls: list[_AgentCall] = []
    telemetry: list[tuple[str, dict[str, object]]] = []

    def fake_build_agent(
        _settings: Settings,
        *,
        output_type: type[Any],
        system_prompt: str | None = None,
        name: str | None = None,
        tier: str = "fast",
        builtin_tools: list[Any] | tuple[Any, ...] = (),
        **_kwargs: object,
    ) -> _AgentCall:
        del system_prompt
        call = _AgentCall(
            name=name or "",
            tier=tier,
            output_type=output_type,
            builtin_tools=list(builtin_tools),
        )
        calls.append(call)
        return call

    async def fake_run(_agent: _AgentCall, _prompt: str) -> _RunResult:
        return _RunResult(
            evidence._CurateResponse(
                facts=[
                    evidence._CurateFact(
                        canonical_text="claim one",
                        statement="candidate 0",
                        source_ref="https://example.test/0",
                    ),
                    evidence._CurateFact(
                        canonical_text="hallucinated claim",
                        statement="Dropped fact.",
                        source_ref="https://example.test/other",
                    ),
                ]
            )
        )

    def fake_logfire_info(event_name: str, **kwargs: object) -> None:
        telemetry.append((event_name, kwargs))

    monkeypatch.setattr(evidence, "build_agent", fake_build_agent)
    monkeypatch.setattr(evidence, "run_vertex_agent_with_retry", fake_run)
    monkeypatch.setattr(evidence.logfire, "info", fake_logfire_info)

    candidates = [
        evidence._ExternalEvidenceCandidate(
            canonical_text="claim one",
            statement=f"candidate {index}",
            source_ref=f"https://example.test/{index}",
        )
        for index in range(12)
    ]

    facts = await evidence._curate_supporting_facts_synthesis(
        candidates,
        Settings(EVIDENCE_SYNTHESIS_CANDIDATE_CAP=10),
    )

    assert [(call.name, call.tier, call.builtin_tools) for call in calls] == [
        ("vibecheck.claims_evidence_curate", "synthesis", [])
    ]
    assert facts["claim one"][0].model_dump(mode="json") == {
        "statement": "candidate 0",
        "source_kind": SourceKind.EXTERNAL.value,
        "source_ref": "https://example.test/0",
    }
    assert "hallucinated claim" not in facts
    assert [event_name for event_name, _kwargs in telemetry] == [
        "vibecheck.evidence.synthesis_prompt_length",
        "vibecheck.evidence.synthesis_curate",
    ]


@pytest.mark.asyncio
async def test_curate_supporting_facts_returns_empty_when_curate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry: list[tuple[str, dict[str, object]]] = []

    def fake_build_agent(
        _settings: Settings,
        *,
        output_type: type[Any],
        system_prompt: str | None = None,
        name: str | None = None,
        tier: str = "fast",
        builtin_tools: list[Any] | tuple[Any, ...] = (),
        **_kwargs: object,
    ) -> _AgentCall:
        del system_prompt
        return _AgentCall(
            name=name or "",
            tier=tier,
            output_type=output_type,
            builtin_tools=list(builtin_tools),
        )

    async def fake_run(_agent: _AgentCall, _prompt: str) -> _RunResult:
        raise RuntimeError("curate model unavailable")

    def fake_logfire_info(event_name: str, **kwargs: object) -> None:
        telemetry.append((event_name, kwargs))

    monkeypatch.setattr(evidence, "build_agent", fake_build_agent)
    monkeypatch.setattr(evidence, "run_vertex_agent_with_retry", fake_run)
    monkeypatch.setattr(evidence.logfire, "info", fake_logfire_info)

    candidates = [
        evidence._ExternalEvidenceCandidate(
            canonical_text="claim one",
            statement="Supported fact.",
            source_ref="https://example.test/source",
        )
    ]

    facts = await evidence._curate_supporting_facts_synthesis(candidates, Settings())

    assert facts == {}
    assert [event for event in telemetry if event[0] == "vibecheck.evidence.curate_failed"] == [
        ("vibecheck.evidence.curate_failed", {"error_type": "RuntimeError"})
    ]


@pytest.mark.asyncio
async def test_fetch_external_evidence_batch_runs_pipeline_with_one_synthesis_call(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    calls: list[_AgentCall] = []

    def fake_build_agent(
        _settings: Settings,
        *,
        output_type: type[Any],
        system_prompt: str | None = None,
        name: str | None = None,
        tier: str = "fast",
        builtin_tools: list[Any] | tuple[Any, ...] = (),
        **_kwargs: object,
    ) -> _AgentCall:
        del system_prompt
        call = _AgentCall(
            name=name or "",
            tier=tier,
            output_type=output_type,
            builtin_tools=list(builtin_tools),
        )
        calls.append(call)
        return call

    async def fake_run(agent: _AgentCall, _prompt: str) -> _RunResult:
        if agent.name == "vibecheck.claims_evidence_cluster":
            return _RunResult(
                evidence._ClusterResponse(
                    groups=[evidence._ClaimGroup(claim_texts=["claim one", "claim two"])]
                )
            )
        if agent.name == "vibecheck.claims_evidence_fetch":
            return _RunResult(
                evidence._ExternalEvidenceResponse(
                    facts=[
                        evidence._ExternalEvidenceItem(
                            canonical_text="claim one",
                            statement="Fetched fact.",
                            source_ref="https://example.test/source",
                        )
                    ]
                ),
                urls=["https://example.test/source"],
            )
        if agent.name == "vibecheck.claims_evidence_sanity":
            return _RunResult(
                evidence._SanityResponse(
                    candidates=[
                        evidence._ExternalEvidenceCandidate(
                            canonical_text="claim one",
                            statement="Fetched fact.",
                            source_ref="https://example.test/source",
                        )
                    ]
                )
            )
        return _RunResult(
            evidence._CurateResponse(
                facts=[
                    evidence._CurateFact(
                        canonical_text="claim one",
                        statement="Fetched fact.",
                        source_ref="https://example.test/source",
                    )
                ]
            )
        )

    monkeypatch.setattr(evidence, "build_agent", fake_build_agent)
    monkeypatch.setattr(evidence, "run_vertex_agent_with_retry", fake_run)

    facts = await evidence.fetch_external_evidence_batch(["claim one", "claim two"], settings)

    assert facts == {
        "claim one": [
            {
                "statement": "Fetched fact.",
                "source_kind": SourceKind.EXTERNAL.value,
                "source_ref": "https://example.test/source",
            }
        ]
    }
    assert sum(1 for call in calls if call.tier == "synthesis") == 1


@pytest.mark.asyncio
async def test_run_claims_evidence_uses_injected_external_fetcher(
    settings: Settings,
) -> None:
    received: list[list[str]] = []

    async def fake_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        received.append(list(claim_texts))
        return {
            claim_texts[0]: [
                {
                    "statement": "Injected lunar fact.",
                    "source_kind": "external",
                    "source_ref": "https://example.test/moon",
                }
            ]
        }

    result = await run_claims_evidence(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=_Payload(_claims_report("The moon is round.")),
        settings=settings,
        external_fetcher=fake_fetcher,
    )

    assert received == [["The moon is round."]]
    claim = result["claims_report"]["deduped_claims"][0]
    assert claim["canonical_text"] == "The moon is round."
    assert claim["supporting_facts"] == [
        {
            "statement": "Injected lunar fact.",
            "source_kind": "external",
            "source_ref": "https://example.test/moon",
        }
    ]


@pytest.mark.asyncio
async def test_run_claims_evidence_merges_from_payload(
    no_external_settings: Settings,
) -> None:
    result = await run_claims_evidence(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=_Payload(_claims_report("The moon is round.")),
        settings=no_external_settings,
        external_fetcher=_no_external_fetcher,
    )

    claim = result["claims_report"]["deduped_claims"][0]
    assert claim["canonical_text"] == "The moon is round."
    assert claim["supporting_facts"] == []
    assert claim["facts_to_verify"] == 1


@pytest.mark.asyncio
async def test_run_claims_evidence_falls_back_to_dedup_slot_when_payload_missing(
    no_external_settings: Settings,
) -> None:
    fake_row = {
        "state": "done",
        "data": {"claims_report": _claims_report("The ocean is blue.").model_dump(mode="json")},
    }

    result = await run_claims_evidence(
        pool=_Pool(fake_row),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=object(),
        settings=no_external_settings,
        external_fetcher=_no_external_fetcher,
    )

    claim = result["claims_report"]["deduped_claims"][0]
    assert claim["canonical_text"] == "The ocean is blue."
    assert claim["supporting_facts"] == []
    assert claim["facts_to_verify"] == 1


@pytest.mark.asyncio
async def test_run_claims_evidence_does_not_load_job_utterances(
    monkeypatch: pytest.MonkeyPatch,
    no_external_settings: Settings,
) -> None:
    async def fail_if_loaded(_pool: object, job_id: object) -> list[object]:
        del job_id
        raise AssertionError("claims evidence should not load source utterances")

    monkeypatch.setattr(
        "src.analyses.claims.evidence_slot.load_job_utterances",
        fail_if_loaded,
        raising=False,
    )

    result = await run_claims_evidence(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=_Payload(_claims_report("The ocean is blue.")),
        settings=no_external_settings,
        external_fetcher=_no_external_fetcher,
    )

    claim = result["claims_report"]["deduped_claims"][0]
    assert claim["canonical_text"] == "The ocean is blue."
    assert claim["supporting_facts"] == []


@pytest.mark.asyncio
async def test_run_claims_evidence_counts_unique_utterances_when_facts_empty(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    claim = DedupedClaim(
        canonical_text="The moon has ice.",
        category=ClaimCategory.POTENTIALLY_FACTUAL,
        occurrence_count=3,
        author_count=2,
        utterance_ids=["u-1", "u-1", "u-2"],
        representative_authors=["alice", "bob"],
    )
    report = ClaimsReport(deduped_claims=[claim], total_claims=3, total_unique=1)

    async def fake_build_supporting_facts(
        *_args: object, **_kwargs: object
    ) -> dict[str, list[Any]]:
        return {}

    monkeypatch.setattr(
        "src.analyses.claims.evidence_slot.build_supporting_facts_by_claim",
        fake_build_supporting_facts,
    )

    result = await run_claims_evidence(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=_Payload(report),
        settings=settings,
    )

    claim_payload = result["claims_report"]["deduped_claims"][0]
    assert claim_payload["supporting_facts"] == []
    assert claim_payload["facts_to_verify"] == 2


@pytest.mark.asyncio
async def test_run_claims_evidence_sets_zero_facts_to_verify_when_fact_exists(
    settings: Settings,
) -> None:
    async def fake_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            claim_texts[0]: [
                {
                    "statement": "NASA confirms water ice near the Moon's poles.",
                    "source_kind": SourceKind.EXTERNAL.value,
                    "source_ref": "https://science.example/moon-ice",
                }
            ]
        }

    result = await run_claims_evidence(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=_Payload(_claims_report("The moon has ice.")),
        settings=settings,
        external_fetcher=fake_fetcher,
    )

    claim_payload = result["claims_report"]["deduped_claims"][0]
    assert claim_payload["supporting_facts"]
    assert claim_payload["facts_to_verify"] == 0


@pytest.mark.asyncio
async def test_run_claims_evidence_sets_zero_facts_to_verify_for_subjective_claim(
    settings: Settings,
) -> None:
    report = ClaimsReport(
        deduped_claims=[
            DedupedClaim(
                canonical_text="I think the moon is beautiful.",
                category=ClaimCategory.SUBJECTIVE,
                occurrence_count=1,
                author_count=1,
                utterance_ids=["u-1"],
                representative_authors=["alice"],
            )
        ],
        total_claims=1,
        total_unique=1,
    )

    result = await run_claims_evidence(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=_Payload(report),
        settings=settings,
    )

    claim_payload = result["claims_report"]["deduped_claims"][0]
    assert claim_payload["supporting_facts"] == []
    assert claim_payload["facts_to_verify"] == 0


@pytest.mark.asyncio
async def test_build_supporting_facts_drops_externally_supplied_utterance_kind_fact(
    settings: Settings,
) -> None:
    claim = DedupedClaim(
        canonical_text="The moon is round.",
        category=ClaimCategory.POTENTIALLY_FACTUAL,
        occurrence_count=1,
        author_count=1,
        utterance_ids=["u-1"],
        representative_authors=["alice"],
    )

    async def hostile_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            claim_texts[0]: [
                {
                    "statement": "The moon is round because a source utterance said so.",
                    "source_kind": SourceKind.UTTERANCE.value,
                    "source_ref": "u-1",
                }
            ]
        }

    facts = await evidence.build_supporting_facts_by_claim(
        [claim],
        settings,
        external_fetcher=hostile_fetcher,
    )

    assert facts == {}


@pytest.mark.asyncio
async def test_build_supporting_facts_returns_only_external_kind(
    settings: Settings,
) -> None:
    claim = DedupedClaim(
        canonical_text="Mars has two moons.",
        category=ClaimCategory.POTENTIALLY_FACTUAL,
        occurrence_count=1,
        author_count=1,
        utterance_ids=["u-1"],
        representative_authors=["alice"],
    )

    async def mixed_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            claim_texts[0]: [
                {
                    "statement": "Phobos and Deimos are Mars's moons.",
                    "source_kind": SourceKind.EXTERNAL.value,
                    "source_ref": "https://science.example/mars-moons",
                },
                {
                    "statement": "A copied utterance is not external evidence.",
                    "source_kind": SourceKind.UTTERANCE.value,
                    "source_ref": "u-other",
                },
            ]
        }

    facts = await evidence.build_supporting_facts_by_claim(
        [claim],
        settings,
        external_fetcher=mixed_fetcher,
    )

    assert [fact.model_dump(mode="json") for fact in facts["Mars has two moons."]] == [
        {
            "statement": "Phobos and Deimos are Mars's moons.",
            "source_kind": SourceKind.EXTERNAL.value,
            "source_ref": "https://science.example/mars-moons",
        }
    ]


def test_inline_tautology_detects_substring_containment() -> None:
    claim = "the company shipped feature x last week"
    statement = "I read that the company shipped feature x last week and it was great."

    assert evidence._is_inline_tautology(statement, claim) is True


def test_inline_tautology_rejects_non_contiguous_topic_overlap() -> None:
    claim = "the company shipped feature x"
    statement = "the company has been busy they shipped feature x today"

    assert evidence._is_inline_tautology(statement, claim) is False


def test_inline_tautology_rejects_short_claim_in_long_statement() -> None:
    claim = "rain falls"
    statement = "Yesterday the heavy rain falls over the valley caused trouble."

    assert evidence._is_inline_tautology(statement, claim) is False


def test_inline_tautology_detects_claim_at_end_of_long_statement() -> None:
    claim = "the moon is round"
    statement = "Recent studies show the moon is round."

    assert evidence._is_inline_tautology(statement, claim) is True


def test_inline_tautology_still_rejects_short_claim_at_edge() -> None:
    claim = "is round"
    statement = "Scientists have concluded that the earth is round after extensive study."

    assert evidence._is_inline_tautology(statement, claim) is False


@pytest.mark.asyncio
async def test_external_supporting_facts_are_not_truncated() -> None:
    long_statement = "x" * 1000

    async def fake_external_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            claim_texts[0]: [
                {
                    "statement": long_statement,
                    "source_kind": SourceKind.EXTERNAL.value,
                    "source_ref": "https://example.com/source",
                }
            ]
        }

    claim = DedupedClaim(
        canonical_text="Mars has two moons.",
        category=ClaimCategory.POTENTIALLY_FACTUAL,
        occurrence_count=1,
        author_count=1,
        utterance_ids=[],
        representative_authors=["alice"],
    )

    settings = Settings(EVIDENCE_MAX_EXTERNAL_CLAIMS=1)

    facts = await evidence.build_supporting_facts_by_claim(
        [claim],
        settings,
        external_fetcher=fake_external_fetcher,
    )

    assert facts["Mars has two moons."][0].statement == long_statement
