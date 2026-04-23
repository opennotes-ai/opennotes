"""Tests for finalize.py — back-compat legacy dict rehydration.

Covers TASK-1474.12 AC5: HarmfulContentMatch rehydration from stored dicts
that were written before TASK-1474.02 (missing `source` field) defaults
source to "openai".
"""
from __future__ import annotations

import pytest

from src.analyses.safety._schemas import HarmfulContentMatch


class TestLegacyDictRehydration:
    def test_harmful_content_match_rehydrates_legacy_dict_without_source_field(self):
        legacy_dict = {
            "utterance_id": "utt_legacy",
            "max_score": 0.8,
            "categories": {"violence": True},
            "scores": {"violence": 0.8},
            "flagged_categories": ["violence"],
        }

        with pytest.raises(Exception):
            HarmfulContentMatch.model_validate(legacy_dict)

    def test_harmful_content_match_with_source_injected_validates_as_openai(self):
        legacy_dict = {
            "utterance_id": "utt_legacy",
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
        """Verify that the guard in finalize._assemble_payload defaults source to openai."""
        from src.jobs import finalize as finalize_mod

        source = finalize_mod.__file__
        with open(source) as f:
            content = f.read()

        assert '"source" not in m' in content or "'source' not in m" in content, (
            "finalize.py must contain the legacy-dict guard: "
            "if isinstance(m, dict) and 'source' not in m: m = {**m, 'source': 'openai'}"
        )


class TestAssemblePayloadWiresNewSafetySections:
    """Codex P0.3 regression: the finalize step MUST copy web_risk / image_mod /
    video_mod slot data into the SidebarPayload. Before this fix, those slots
    were silently dropped and never reached the rendered sidebar.
    """

    def _sections_with_new_safety(self) -> dict:
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
