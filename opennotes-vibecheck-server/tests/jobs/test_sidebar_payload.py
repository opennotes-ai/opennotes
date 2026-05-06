"""Tests for sidebar_payload.py — shared payload assembler.

Covers AC1: public helper assembles SidebarPayload from any SectionSlot map
using neutral defaults for missing, pending, running, or failed slots.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from src.analyses.safety._schemas import SafetyLevel
from src.analyses.schemas import (
    SectionSlot,
    SectionSlug,
    SectionState,
    SidebarPayload,
    UtteranceAnchor,
)
from src.jobs.sidebar_payload import (
    assemble_sidebar_payload,
    payload_for_url_cache,
)


def _done_slot(data: dict[str, Any] | None = None) -> SectionSlot:
    return SectionSlot(state=SectionState.DONE, attempt_id=uuid4(), data=data)


def _pending_slot() -> SectionSlot:
    return SectionSlot(state=SectionState.PENDING, attempt_id=uuid4(), data=None)


def _failed_slot() -> SectionSlot:
    return SectionSlot(state=SectionState.FAILED, attempt_id=uuid4(), data=None)


def _minimal_done_sections() -> dict[SectionSlug, SectionSlot]:
    """Return a complete set of done slots with empty/default data."""
    return {
        SectionSlug.SAFETY_MODERATION: _done_slot({"harmful_content_matches": []}),
        SectionSlug.SAFETY_WEB_RISK: _done_slot({"findings": []}),
        SectionSlug.SAFETY_IMAGE_MODERATION: _done_slot({"matches": []}),
        SectionSlug.SAFETY_VIDEO_MODERATION: _done_slot({"matches": []}),
        SectionSlug.TONE_DYNAMICS_FLASHPOINT: _done_slot({"flashpoint_matches": []}),
        SectionSlug.TONE_DYNAMICS_SCD: _done_slot(
            {
                "scd": {
                    "summary": "",
                    "tone_labels": [],
                    "per_speaker_notes": {},
                    "insufficient_conversation": True,
                }
            }
        ),
        SectionSlug.FACTS_CLAIMS_DEDUP: _done_slot(
            {
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                }
            }
        ),
        SectionSlug.FACTS_CLAIMS_EVIDENCE: _done_slot(
            {
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                }
            }
        ),
        SectionSlug.FACTS_CLAIMS_PREMISES: _done_slot(
            {
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                }
            }
        ),
        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO: _done_slot({"known_misinformation": []}),
        SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT: _done_slot(
            {
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0.0,
                    "negative_pct": 0.0,
                    "neutral_pct": 0.0,
                    "mean_valence": 0.0,
                }
            }
        ),
        SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE: _done_slot({"subjective_claims": []}),
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS: _done_slot(
            {
                "trends_oppositions_report": {
                    "trends": [],
                    "oppositions": [],
                    "input_cluster_count": 0,
                    "skipped_for_cap": 0,
                }
            }
        ),
    }


class TestAssembleSidebarPayload:
    def test_returns_sidebar_payload_with_source_url(self):
        sidebar = assemble_sidebar_payload("https://example.com", {})

        assert isinstance(sidebar, SidebarPayload)
        assert sidebar.source_url == "https://example.com"

    def test_missing_sections_get_empty_defaults(self):
        """Any missing slot should be filled with empty_section_data defaults."""
        sidebar = assemble_sidebar_payload("https://example.com", {})

        assert sidebar.safety.harmful_content_matches == []
        assert sidebar.web_risk.findings == []
        assert sidebar.image_moderation.matches == []
        assert sidebar.video_moderation.matches == []
        assert sidebar.tone_dynamics.flashpoint_matches == []
        assert sidebar.facts_claims.claims_report.deduped_claims == []
        assert sidebar.opinions_sentiments.opinions_report.sentiment_stats.per_utterance == []
        assert sidebar.opinions_sentiments.trends_oppositions is None
        assert sidebar.headline is None
        assert sidebar.utterances == []

    def test_no_trends_oppositions_slot_returns_none(self):
        sections = _minimal_done_sections()
        sections.pop(SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS)

        sidebar = assemble_sidebar_payload("https://example.com", sections)

        assert sidebar.opinions_sentiments.trends_oppositions is None
        assert SidebarPayload.model_validate(sidebar.model_dump(mode="json"))

    def test_failed_trends_oppositions_slot_returns_none_and_still_validates(self):
        sections = _minimal_done_sections()
        sections[SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS] = _failed_slot()

        sidebar = assemble_sidebar_payload("https://example.com", sections)

        assert sidebar.opinions_sentiments.trends_oppositions is None
        assert SidebarPayload.model_validate(sidebar.model_dump(mode="json"))

    def test_pending_slot_gets_empty_defaults(self):
        """Pending slots are not done; should get neutral defaults."""
        sections = _minimal_done_sections()
        sections[SectionSlug.SAFETY_MODERATION] = _pending_slot()

        sidebar = assemble_sidebar_payload("https://example.com", sections)

        assert sidebar.safety.harmful_content_matches == []
        assert sidebar.safety.recommendation is None

    def test_failed_slot_gets_empty_defaults(self):
        """Failed slots are not done; should get neutral defaults."""
        sections = _minimal_done_sections()
        sections[SectionSlug.FACTS_CLAIMS_DEDUP] = _failed_slot()

        sidebar = assemble_sidebar_payload("https://example.com", sections)

        assert sidebar.facts_claims.claims_report.deduped_claims == []

    def test_done_slot_data_flows_through(self):
        sections = _minimal_done_sections()
        sections[SectionSlug.SAFETY_WEB_RISK] = _done_slot(
            {"findings": [{"url": "https://bad.example", "threat_types": ["MALWARE"]}]}
        )

        sidebar = assemble_sidebar_payload("https://example.com", sections)

        assert len(sidebar.web_risk.findings) == 1
        assert sidebar.web_risk.findings[0].threat_types == ["MALWARE"]

    def test_facts_slots_merge_into_deduped_claims_by_canonical_text(self):
        sections = _minimal_done_sections()
        sections[SectionSlug.FACTS_CLAIMS_DEDUP] = _done_slot(
            {
                "claims_report": {
                    "deduped_claims": [
                        {
                            "canonical_text": "The sky is blue.",
                            "occurrence_count": 1,
                            "author_count": 1,
                            "utterance_ids": ["u-1"],
                            "representative_authors": ["alice"],
                        }
                    ],
                    "total_claims": 1,
                    "total_unique": 1,
                }
            }
        )
        sections[SectionSlug.FACTS_CLAIMS_EVIDENCE] = _done_slot(
            {
                "claims_report": {
                    "deduped_claims": [
                        {
                            "canonical_text": "The sky is blue.",
                            "occurrence_count": 1,
                            "author_count": 1,
                            "utterance_ids": ["u-1"],
                            "representative_authors": ["alice"],
                            "supporting_facts": [
                                {
                                    "statement": "Observed data",
                                    "source_kind": "utterance",
                                    "source_ref": "u-1",
                                }
                            ],
                        }
                    ],
                    "total_claims": 1,
                    "total_unique": 1,
                }
            }
        )
        sections[SectionSlug.FACTS_CLAIMS_PREMISES] = _done_slot(
            {
                "claims_report": {
                    "deduped_claims": [
                        {
                            "canonical_text": "The sky is blue.",
                            "occurrence_count": 1,
                            "author_count": 1,
                            "utterance_ids": ["u-1"],
                            "representative_authors": ["alice"],
                            "premise_ids": ["premise_abcdef123456"],
                        }
                    ],
                    "total_claims": 1,
                    "total_unique": 1,
                    "premises": {
                        "premises": {
                            "premise_abcdef123456": {
                                "premise_id": "premise_abcdef123456",
                                "statement": "Light appears blue to humans.",
                            }
                        }
                    },
                }
            }
        )

        sidebar = assemble_sidebar_payload("https://example.com", sections)

        facts = sidebar.facts_claims.claims_report
        assert facts.deduped_claims[0].supporting_facts[0].source_ref == "u-1"
        assert facts.deduped_claims[0].premise_ids == ["premise_abcdef123456"]
        assert facts.premises is not None
        assert "premise_abcdef123456" in facts.premises.premises

    def test_safety_recommendation_dict_parses(self):
        sections = _minimal_done_sections()
        sidebar = assemble_sidebar_payload(
            "https://example.com",
            sections,
            safety_recommendation={
                "level": "caution",
                "rationale": "Some inputs were unavailable.",
                "top_signals": ["web risk unavailable"],
                "unavailable_inputs": ["web_risk"],
            },
        )

        assert sidebar.safety.recommendation is not None
        assert sidebar.safety.recommendation.level == SafetyLevel.CAUTION
        assert sidebar.safety.recommendation.unavailable_inputs == ["web_risk"]

    def test_safety_recommendation_json_string_parses(self):
        sections = _minimal_done_sections()
        sidebar = assemble_sidebar_payload(
            "https://example.com",
            sections,
            safety_recommendation=json.dumps(
                {
                    "level": "safe",
                    "rationale": "All clear.",
                    "top_signals": [],
                    "unavailable_inputs": [],
                }
            ),
        )

        assert sidebar.safety.recommendation is not None
        assert sidebar.safety.recommendation.level == SafetyLevel.SAFE

    def test_null_safety_recommendation_stays_none(self):
        sidebar = assemble_sidebar_payload("https://example.com", _minimal_done_sections(), None)
        assert sidebar.safety.recommendation is None

    def test_headline_summary_dict_parses(self):
        sections = _minimal_done_sections()
        sidebar = assemble_sidebar_payload(
            "https://example.com",
            sections,
            headline_summary={
                "text": "A perceptive opening line.",
                "kind": "synthesized",
                "unavailable_inputs": [],
            },
        )

        assert sidebar.headline is not None
        assert sidebar.headline.text == "A perceptive opening line."
        assert sidebar.headline.kind == "synthesized"

    def test_headline_summary_json_string_parses(self):
        sections = _minimal_done_sections()
        sidebar = assemble_sidebar_payload(
            "https://example.com",
            sections,
            headline_summary=json.dumps(
                {"text": "Stock phrase.", "kind": "stock", "unavailable_inputs": ["scd"]}
            ),
        )

        assert sidebar.headline is not None
        assert sidebar.headline.kind == "stock"
        assert sidebar.headline.unavailable_inputs == ["scd"]

    def test_null_headline_summary_stays_none(self):
        sidebar = assemble_sidebar_payload(
            "https://example.com", _minimal_done_sections(), headline_summary=None
        )
        assert sidebar.headline is None

    def test_utterances_default_to_empty_list(self):
        sidebar = assemble_sidebar_payload("https://example.com", _minimal_done_sections())
        assert sidebar.utterances == []

    def test_utterances_passed_through(self):
        anchors = [
            UtteranceAnchor(position=1, utterance_id="comment-0-aaa"),
            UtteranceAnchor(position=2, utterance_id="comment-1-bbb"),
        ]
        sidebar = assemble_sidebar_payload(
            "https://example.com", _minimal_done_sections(), utterances=anchors
        )

        assert [a.utterance_id for a in sidebar.utterances] == ["comment-0-aaa", "comment-1-bbb"]

    def test_legacy_harmful_content_match_without_source_defaults_to_openai(self):
        """AC from TASK-1474.12: legacy dicts missing `source` default to openai."""
        sections = _minimal_done_sections()
        sections[SectionSlug.SAFETY_MODERATION] = _done_slot(
            {
                "harmful_content_matches": [
                    {
                        "utterance_id": "utt_legacy",
                        "utterance_text": "legacy text",
                        "max_score": 0.8,
                        "categories": {"violence": True},
                        "scores": {"violence": 0.8},
                        "flagged_categories": ["violence"],
                    }
                ]
            }
        )

        sidebar = assemble_sidebar_payload("https://example.com", sections)

        assert sidebar.safety.harmful_content_matches[0].source == "openai"

    def test_explicit_harmful_content_source_preserved(self):
        sections = _minimal_done_sections()
        sections[SectionSlug.SAFETY_MODERATION] = _done_slot(
            {
                "harmful_content_matches": [
                    {
                        "utterance_id": "utt_modern",
                        "utterance_text": "modern text",
                        "max_score": 0.7,
                        "categories": {"hate": True},
                        "scores": {"hate": 0.7},
                        "flagged_categories": ["hate"],
                        "source": "gcp",
                    }
                ]
            }
        )

        sidebar = assemble_sidebar_payload("https://example.com", sections)

        assert sidebar.safety.harmful_content_matches[0].source == "gcp"

    def test_image_moderation_matches_flow_through(self):
        sections = _minimal_done_sections()
        sections[SectionSlug.SAFETY_IMAGE_MODERATION] = _done_slot(
            {
                "matches": [
                    {
                        "utterance_id": "u1",
                        "image_url": "https://example.com/img.jpg",
                        "adult": 1.0,
                        "violence": 0.0,
                        "racy": 0.0,
                        "medical": 0.0,
                        "spoof": 0.0,
                        "flagged": True,
                        "max_likelihood": 1.0,
                    }
                ]
            }
        )

        sidebar = assemble_sidebar_payload("https://example.com", sections)

        assert len(sidebar.image_moderation.matches) == 1
        assert sidebar.image_moderation.matches[0].flagged is True

    def test_trends_oppositions_slot_done_populates_field(self):
        sections = _minimal_done_sections()
        sections[SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS] = _done_slot(
            {
                "trends_oppositions_report": {
                    "trends": [
                        {"label": "trend", "cluster_texts": ["c1"], "summary": "desc"},
                    ],
                    "oppositions": [
                        {
                            "topic": "topic-1",
                            "supporting_cluster_texts": ["c1"],
                            "opposing_cluster_texts": ["c2"],
                            "note": "note",
                        }
                    ],
                    "input_cluster_count": 2,
                    "skipped_for_cap": 0,
                }
            }
        )

        sidebar = assemble_sidebar_payload("https://example.com", sections)
        payload = SidebarPayload.model_validate(sidebar.model_dump(mode="json"))

        assert payload.opinions_sentiments.trends_oppositions is not None
        assert payload.opinions_sentiments.trends_oppositions.trends[0].label == "trend"
        assert (
            payload.opinions_sentiments.trends_oppositions.oppositions[0].topic
            == "topic-1"
        )

    def test_video_moderation_matches_flow_through(self):
        sections = _minimal_done_sections()
        sections[SectionSlug.SAFETY_VIDEO_MODERATION] = _done_slot(
            {
                "matches": [
                    {
                        "utterance_id": "u2",
                        "video_url": "https://example.com/vid.mp4",
                        "frame_findings": [],
                        "flagged": True,
                        "max_likelihood": 1.0,
                    }
                ]
            }
        )

        sidebar = assemble_sidebar_payload("https://example.com", sections)

        assert len(sidebar.video_moderation.matches) == 1
        assert sidebar.video_moderation.matches[0].flagged is True


class TestPayloadForUrlCache:
    def test_strips_utterance_anchors(self):
        sections = _minimal_done_sections()
        sidebar = assemble_sidebar_payload(
            "https://example.com",
            sections,
            utterances=[
                UtteranceAnchor(position=1, utterance_id="comment-0-aaa"),
            ],
        )

        assert sidebar.utterances[0].utterance_id == "comment-0-aaa"
        cached = json.loads(payload_for_url_cache(sidebar))
        assert cached["utterances"] == []

    def test_preserves_other_fields(self):
        sections = _minimal_done_sections()
        sidebar = assemble_sidebar_payload(
            "https://example.com",
            sections,
            headline_summary={
                "text": "Headline",
                "kind": "synthesized",
                "unavailable_inputs": [],
            },
        )

        cached = json.loads(payload_for_url_cache(sidebar))
        assert cached["headline"]["text"] == "Headline"
        assert cached["source_url"] == "https://example.com"
        assert cached["safety"]["harmful_content_matches"] == []
