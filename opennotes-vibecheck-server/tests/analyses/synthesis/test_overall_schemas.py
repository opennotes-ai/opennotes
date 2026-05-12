from __future__ import annotations

from datetime import UTC, datetime

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.opinions._schemas import OpinionsReport, SentimentStatsReport
from src.analyses.schemas import (
    FactsClaimsSection,
    OpinionsSection,
    SafetySection,
    SidebarPayload,
    ToneDynamicsSection,
)
from src.analyses.synthesis._overall_schemas import OverallDecision, OverallVerdict
from src.analyses.tone._scd_schemas import SCDReport


def _minimal_sidebar_payload(**overrides: object) -> SidebarPayload:
    payload = {
        "source_url": "https://example.com/post",
        "scraped_at": datetime(2026, 1, 1, tzinfo=UTC),
        "safety": SafetySection(),
        "tone_dynamics": ToneDynamicsSection(
            scd=SCDReport(summary="", insufficient_conversation=True)
        ),
        "facts_claims": FactsClaimsSection(
            claims_report=ClaimsReport(
                deduped_claims=[],
                total_claims=0,
                total_unique=0,
            )
        ),
        "opinions_sentiments": OpinionsSection(
            opinions_report=OpinionsReport(
                sentiment_stats=SentimentStatsReport(
                    per_utterance=[],
                    positive_pct=0.0,
                    negative_pct=0.0,
                    neutral_pct=0.0,
                    mean_valence=0.0,
                ),
                subjective_claims=[],
            )
        ),
    }
    payload.update(overrides)
    return SidebarPayload(**payload)


def test_overall_decision_status_defaults_to_final() -> None:
    decision = OverallDecision.model_validate(
        {"verdict": "flag", "reason": "Misleading framing"}
    )

    assert decision.verdict is OverallVerdict.FLAG
    assert decision.status == "final"
    assert decision.model_dump(mode="json") == {
        "verdict": "flag",
        "reason": "Misleading framing",
        "status": "final",
    }


def test_sidebar_payload_round_trips_null_overall() -> None:
    payload = _minimal_sidebar_payload(overall=None)

    parsed = SidebarPayload.model_validate(payload.model_dump(mode="json"))

    assert parsed.overall is None


def test_sidebar_payload_round_trips_populated_overall() -> None:
    payload = _minimal_sidebar_payload(
        overall=OverallDecision(verdict=OverallVerdict.PASS, reason="No notable concerns")
    )

    parsed = SidebarPayload.model_validate(payload.model_dump(mode="json"))

    assert parsed.overall is not None
    assert parsed.overall.verdict is OverallVerdict.PASS
    assert parsed.overall.reason == "No notable concerns"
    assert parsed.overall.status == "final"
