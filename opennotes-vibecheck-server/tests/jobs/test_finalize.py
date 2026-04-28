"""Tests for finalize.py — back-compat legacy dict rehydration.

Covers TASK-1474.12 AC5: HarmfulContentMatch rehydration from stored dicts
that were written before TASK-1474.02 (missing `source` field) defaults
source to "openai".
"""
from __future__ import annotations

from typing import Any

from src.analyses.safety._schemas import HarmfulContentMatch
from src.analyses.schemas import SectionSlug


class TestLegacyDictRehydration:
    def test_harmful_content_match_rehydrates_legacy_dict_without_source_field(self):
        legacy_dict = {
            "utterance_id": "utt_legacy",
            "utterance_text": "legacy text",
            "max_score": 0.8,
            "categories": {"violence": True},
            "scores": {"violence": 0.8},
            "flagged_categories": ["violence"],
        }

        match = HarmfulContentMatch.model_validate(legacy_dict)

        assert match.source == "openai"

    def test_harmful_content_match_with_source_injected_validates_as_openai(self):
        legacy_dict = {
            "utterance_id": "utt_legacy",
            "utterance_text": "legacy text",
            "max_score": 0.8,
            "categories": {"violence": True},
            "scores": {"violence": 0.8},
            "flagged_categories": ["violence"],
        }

        m = {**legacy_dict, "source": "openai"} if "source" not in legacy_dict else legacy_dict
        match = HarmfulContentMatch.model_validate(m)

        assert match.utterance_id == "utt_legacy"
        assert match.source == "openai"
        assert match.max_score == 0.8

    def test_harmful_content_match_with_explicit_source_gcp_preserved(self):
        modern_dict = {
            "utterance_id": "utt_modern",
            "utterance_text": "modern text",
            "max_score": 0.7,
            "categories": {"hate": True},
            "scores": {"hate": 0.7},
            "flagged_categories": ["hate"],
            "source": "gcp",
        }

        m = {**modern_dict, "source": "openai"} if "source" not in modern_dict else modern_dict
        match = HarmfulContentMatch.model_validate(m)

        assert match.source == "gcp"

    def test_finalize_safety_guard_handles_legacy_dict(self):
        """Verify that _assemble_payload defaults legacy safety matches to openai."""
        from src.jobs.finalize import _assemble_payload

        sections = TestAssemblePayloadWiresNewSafetySections()._sections_with_new_safety()
        sections[SectionSlug.SAFETY_MODERATION].data = {
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

        sidebar = _assemble_payload("https://test", sections)

        assert sidebar.safety.harmful_content_matches[0].source == "openai"


class TestAssemblePayloadWiresNewSafetySections:
    """Codex P0.3 regression: the finalize step MUST copy web_risk / image_mod /
    video_mod slot data into the SidebarPayload. Before this fix, those slots
    were silently dropped and never reached the rendered sidebar.
    """

    def _sections_with_new_safety(self) -> dict[Any, Any]:
        from uuid import uuid4

        from src.analyses.schemas import (
            SectionSlot,
            SectionSlug,
            SectionState,
        )

        def slot(data):
            return SectionSlot(state=SectionState.DONE, attempt_id=uuid4(), data=data)

        return {
            SectionSlug.SAFETY_MODERATION: slot({"harmful_content_matches": []}),
            SectionSlug.SAFETY_WEB_RISK: slot({
                "findings": [
                    {"url": "https://example.com/bad", "threat_types": ["MALWARE"]}
                ]
            }),
            SectionSlug.SAFETY_IMAGE_MODERATION: slot({
                "matches": [
                    {
                        "utterance_id": "u1",
                        "image_url": "https://example.com/img.jpg",
                        "adult": 1.0, "violence": 0.0, "racy": 0.0,
                        "medical": 0.0, "spoof": 0.0,
                        "flagged": True, "max_likelihood": 1.0,
                    }
                ]
            }),
            SectionSlug.SAFETY_VIDEO_MODERATION: slot({
                "matches": [
                    {
                        "utterance_id": "u2",
                        "video_url": "https://example.com/vid.mp4",
                        "frame_findings": [],
                        "flagged": True, "max_likelihood": 1.0,
                    }
                ]
            }),
            SectionSlug.TONE_DYNAMICS_FLASHPOINT: slot({"flashpoint_matches": []}),
            SectionSlug.TONE_DYNAMICS_SCD: slot({
                "scd": {
                    "summary": "",
                    "tone_labels": [],
                    "per_speaker_notes": {},
                    "insufficient_conversation": True,
                }
            }),
            SectionSlug.FACTS_CLAIMS_DEDUP: slot({
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                }
            }),
            SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO: slot({"known_misinformation": []}),
            SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT: slot({
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0.0,
                    "negative_pct": 0.0,
                    "neutral_pct": 0.0,
                    "mean_valence": 0.0,
                }
            }),
            SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE: slot({"subjective_claims": []}),
        }

    def test_web_risk_findings_flow_through_to_sidebar_payload(self):
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload("https://test", self._sections_with_new_safety())
        assert len(sidebar.web_risk.findings) == 1
        assert sidebar.web_risk.findings[0].threat_types == ["MALWARE"]

    def test_image_moderation_matches_flow_through_to_sidebar_payload(self):
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload("https://test", self._sections_with_new_safety())
        assert len(sidebar.image_moderation.matches) == 1
        assert sidebar.image_moderation.matches[0].flagged is True

    def test_video_moderation_matches_flow_through_to_sidebar_payload(self):
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload("https://test", self._sections_with_new_safety())
        assert len(sidebar.video_moderation.matches) == 1
        assert sidebar.video_moderation.matches[0].flagged is True

    def test_all_new_sections_empty_by_default(self):
        """Empty slot data → default-empty sections (no spurious findings)."""
        from uuid import uuid4

        from src.analyses.schemas import SectionSlot, SectionSlug, SectionState
        from src.jobs.finalize import _assemble_payload

        empty = self._sections_with_new_safety()
        # Overwrite the three new sections with empty lists
        for slug, empty_data in [
            (SectionSlug.SAFETY_WEB_RISK, {"findings": []}),
            (SectionSlug.SAFETY_IMAGE_MODERATION, {"matches": []}),
            (SectionSlug.SAFETY_VIDEO_MODERATION, {"matches": []}),
        ]:
            empty[slug] = SectionSlot(
                state=SectionState.DONE, attempt_id=uuid4(), data=empty_data
            )

        sidebar = _assemble_payload("https://test", empty)
        assert sidebar.web_risk.findings == []
        assert sidebar.image_moderation.matches == []
        assert sidebar.video_moderation.matches == []

    def test_safety_recommendation_column_flows_into_sidebar_payload(self):
        from src.analyses.safety._schemas import SafetyLevel
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload(
            "https://test",
            self._sections_with_new_safety(),
            {
                "level": "caution",
                "rationale": "Some inputs were unavailable.",
                "top_signals": ["web risk unavailable"],
                "unavailable_inputs": ["web_risk"],
            },
        )

        assert sidebar.safety.recommendation is not None
        assert sidebar.safety.recommendation.level == SafetyLevel.CAUTION
        assert sidebar.safety.recommendation.unavailable_inputs == ["web_risk"]

    def test_null_safety_recommendation_stays_none(self):
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload("https://test", self._sections_with_new_safety(), None)

        assert sidebar.safety.recommendation is None

    def test_headline_summary_column_flows_into_sidebar_payload(self):
        # TASK-1508.04.01: finalize inflates headline_summary onto SidebarPayload.
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload(
            "https://test",
            self._sections_with_new_safety(),
            None,
            {
                "text": "A perceptive opening line.",
                "kind": "synthesized",
                "unavailable_inputs": [],
            },
        )

        assert sidebar.headline is not None
        assert sidebar.headline.text == "A perceptive opening line."
        assert sidebar.headline.kind == "synthesized"

    def test_null_headline_summary_stays_none(self):
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload(
            "https://test", self._sections_with_new_safety(), None, None
        )

        assert sidebar.headline is None

    def test_headline_summary_accepts_json_string(self):
        # asyncpg may return the JSONB column as a raw string depending on codec
        # configuration; finalize must json.loads strings before validating.
        import json as _json

        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload(
            "https://test",
            self._sections_with_new_safety(),
            None,
            _json.dumps(
                {
                    "text": "Stock phrase.",
                    "kind": "stock",
                    "unavailable_inputs": ["scd"],
                }
            ),
        )

        assert sidebar.headline is not None
        assert sidebar.headline.kind == "stock"
        assert sidebar.headline.unavailable_inputs == ["scd"]

    def test_utterance_anchors_flow_into_sidebar_payload(self):
        from src.analyses.schemas import UtteranceAnchor
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload(
            "https://test",
            self._sections_with_new_safety(),
            utterances=[
                UtteranceAnchor(position=1, utterance_id="comment-0-aaa"),
                UtteranceAnchor(position=2, utterance_id="comment-1-bbb"),
            ],
        )

        assert [anchor.utterance_id for anchor in sidebar.utterances] == [
            "comment-0-aaa",
            "comment-1-bbb",
        ]
