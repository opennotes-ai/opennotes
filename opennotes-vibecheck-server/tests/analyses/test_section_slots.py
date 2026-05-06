from __future__ import annotations

from uuid import uuid4

import pytest

from src.analyses.claims._claims_schemas import Claim, ClaimsReport, DedupedClaim
from src.analyses.opinions._schemas import SentimentScore, SentimentStatsReport, SubjectiveClaim
from src.analyses.tone._flashpoint_schemas import FlashpointMatch, RiskLevel
from src.analyses.tone._scd_schemas import SCDReport, SpeakerArc
from src.config import Settings


class _Acquire:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    async def __aenter__(self) -> _Conn:
        return _Conn(self._rows)

    async def __aexit__(self, *args: object) -> None:
        return None


class _Conn:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    async def fetch(self, *_args: object) -> list[dict[str, object]]:
        return self._rows

    async def fetchval(self, *_args: object) -> object:
        if not self._rows:
            return None
        return self._rows[0].get("utterance_stream_type")


class _Pool:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def acquire(self) -> _Acquire:
        return _Acquire(self._rows)


def _pool_with_two_utterances() -> _Pool:
    return _Pool(
        [
            {
                "utterance_id": "u-1",
                "kind": "post",
                "text": "The checkout flow is broken for everyone.",
                "author": "alice",
                "timestamp_at": None,
                "parent_id": None,
            },
            {
                "utterance_id": "u-2",
                "kind": "comment",
                "text": "That release was careless and made the product worse.",
                "author": "bob",
                "timestamp_at": None,
                "parent_id": "u-1",
            },
        ]
    )


def _settings() -> Settings:
    return Settings()


async def test_run_flashpoint_loads_persisted_utterances_and_returns_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.analyses.tone import flashpoint_slot

    async def fake_detect(utterances, settings):
        assert [u.utterance_id for u in utterances] == ["u-1", "u-2"]
        return [
            None,
            FlashpointMatch(
                utterance_id="u-2",
                derailment_score=82,
                risk_level=RiskLevel.HOSTILE,
                reasoning="The reply escalates into a direct attack.",
                context_messages=1,
            ),
        ]

    monkeypatch.setattr(flashpoint_slot, "detect_flashpoints_bulk", fake_detect)

    result = await flashpoint_slot.run_flashpoint(
        _pool_with_two_utterances(), uuid4(), uuid4(), object(), _settings()
    )

    assert result == {
        "flashpoint_matches": [
            {
                "scan_type": "conversation_flashpoint",
                "utterance_id": "u-2",
                "derailment_score": 82,
                "risk_level": "Hostile",
                "reasoning": "The reply escalates into a direct attack.",
                "context_messages": 1,
            }
        ]
    }


async def test_run_scd_loads_persisted_utterances_and_returns_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.analyses.tone import scd_slot

    async def fake_analyze(utterances, settings, *, utterance_stream_type=None):
        del utterance_stream_type
        assert [u.author for u in utterances] == ["alice", "bob"]
        return SCDReport(
            narrative="Bob escalates after Alice reports a concrete issue.",
            speaker_arcs=[
                SpeakerArc(
                    speaker="bob",
                    note="Moves from response to criticism.",
                    utterance_id_range=[2, 2],
                )
            ],
            summary="The exchange turns critical after the initial report.",
            tone_labels=["critical"],
            per_speaker_notes={"bob": "Critical response."},
            insufficient_conversation=False,
        )

    monkeypatch.setattr(scd_slot, "analyze_scd", fake_analyze)

    result = await scd_slot.run_scd(
        _pool_with_two_utterances(), uuid4(), uuid4(), object(), _settings()
    )

    assert result["scd"]["summary"] == "The exchange turns critical after the initial report."
    assert result["scd"]["tone_labels"] == ["critical"]
    assert result["scd"]["speaker_arcs"][0]["speaker"] == "bob"


async def test_run_claims_dedup_extracts_and_dedupes_persisted_utterances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.analyses.claims import dedupe_slot

    async def fake_extract(utterances, settings):
        assert [u.utterance_id for u in utterances] == ["u-1", "u-2"]
        return [
            [Claim(claim_text="Checkout is broken.", utterance_id="u-1", confidence=0.92)],
            [Claim(claim_text="Checkout is broken for everyone.", utterance_id="u-2", confidence=0.88)],
        ]

    async def fake_dedupe(claims, utterances, settings):
        assert [claim.utterance_id for claim in claims] == ["u-1", "u-2"]
        return ClaimsReport(
            deduped_claims=[
                DedupedClaim(
                    canonical_text="Checkout is broken.",
                    occurrence_count=2,
                    author_count=2,
                    utterance_ids=["u-1", "u-2"],
                    representative_authors=["alice", "bob"],
                )
            ],
            total_claims=2,
            total_unique=1,
        )

    monkeypatch.setattr(dedupe_slot, "extract_claims_bulk", fake_extract)
    monkeypatch.setattr(dedupe_slot, "dedupe_claims", fake_dedupe)

    result = await dedupe_slot.run_claims_dedup(
        _pool_with_two_utterances(), uuid4(), uuid4(), object(), _settings()
    )

    assert result["claims_report"]["total_claims"] == 2
    assert result["claims_report"]["deduped_claims"][0]["occurrence_count"] == 2


async def test_run_sentiment_loads_persisted_utterances_and_returns_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.analyses.opinions import sentiment_slot

    async def fake_sentiment(utterances, *, settings=None):
        assert [u.text for u in utterances] == [
            "The checkout flow is broken for everyone.",
            "That release was careless and made the product worse.",
        ]
        return SentimentStatsReport(
            per_utterance=[
                SentimentScore(utterance_id="u-1", label="negative", valence=-0.6),
                SentimentScore(utterance_id="u-2", label="negative", valence=-0.8),
            ],
            positive_pct=0.0,
            negative_pct=100.0,
            neutral_pct=0.0,
            mean_valence=-0.7,
        )

    monkeypatch.setattr(sentiment_slot, "compute_sentiment_stats", fake_sentiment)

    result = await sentiment_slot.run_sentiment(
        _pool_with_two_utterances(), uuid4(), uuid4(), object(), _settings()
    )

    assert result["sentiment_stats"]["negative_pct"] == 100.0
    assert result["sentiment_stats"]["per_utterance"][1]["utterance_id"] == "u-2"


async def test_run_subjective_loads_persisted_utterances_and_returns_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.analyses.opinions import subjective_slot

    async def fake_subjective(utterances, *, settings=None):
        assert [u.utterance_id for u in utterances] == ["u-1", "u-2"]
        return [
            [],
            [
                SubjectiveClaim(
                    claim_text="The release made the product worse.",
                    utterance_id="u-2",
                    stance="evaluates",
                )
            ],
        ]

    monkeypatch.setattr(subjective_slot, "extract_subjective_claims_bulk", fake_subjective)

    result = await subjective_slot.run_subjective(
        _pool_with_two_utterances(), uuid4(), uuid4(), object(), _settings()
    )

    assert result == {
        "subjective_claims": [
            {
                "claim_text": "The release made the product worse.",
                "utterance_id": "u-2",
                "stance": "evaluates",
            }
        ]
    }
