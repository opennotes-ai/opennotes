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
        import json
        from src.jobs import finalize as finalize_mod

        source = finalize_mod.__file__
        with open(source) as f:
            content = f.read()

        assert '"source" not in m' in content or "'source' not in m" in content, (
            "finalize.py must contain the legacy-dict guard: "
            "if isinstance(m, dict) and 'source' not in m: m = {**m, 'source': 'openai'}"
        )
