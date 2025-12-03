from dataclasses import dataclass
from enum import Enum


class ScoringTier(str, Enum):
    MINIMAL = "minimal"
    LIMITED = "limited"
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    FULL = "full"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TierThresholds:
    min_notes: int
    max_notes: int | None
    description: str
    scorers: list[str]
    requires_full_pipeline: bool = False
    enable_clustering: bool = False
    confidence_warnings: bool = False


TIER_CONFIGURATIONS = {
    ScoringTier.MINIMAL: TierThresholds(
        min_notes=0,
        max_notes=200,
        description="Minimal tier: Bayesian Average for bootstrap phase (0-200 notes)",
        scorers=["BayesianAverageScorer"],
        requires_full_pipeline=False,
        enable_clustering=False,
        confidence_warnings=True,
    ),
    ScoringTier.LIMITED: TierThresholds(
        min_notes=200,
        max_notes=1000,
        description="Limited tier: MFCoreScorer with warnings (200-1000 notes)",
        scorers=["MFCoreScorer"],
        requires_full_pipeline=False,
        enable_clustering=False,
        confidence_warnings=True,
    ),
    ScoringTier.BASIC: TierThresholds(
        min_notes=1000,
        max_notes=5000,
        description="Basic tier: Full MFCoreScorer (1000-5000 notes)",
        scorers=["MFCoreScorer"],
        requires_full_pipeline=False,
        enable_clustering=False,
        confidence_warnings=False,
    ),
    ScoringTier.INTERMEDIATE: TierThresholds(
        min_notes=5000,
        max_notes=10000,
        description="Intermediate tier: Core + Expansion scorers (5000-10000 notes)",
        scorers=["MFCoreScorer", "MFExpansionScorer"],
        requires_full_pipeline=False,
        enable_clustering=False,
        confidence_warnings=False,
    ),
    ScoringTier.ADVANCED: TierThresholds(
        min_notes=10000,
        max_notes=50000,
        description="Advanced tier: Core + Expansion + Group scorers (10000-50000 notes)",
        scorers=["MFCoreScorer", "MFExpansionScorer", "MFGroupScorer", "MFExpansionPlusScorer"],
        requires_full_pipeline=True,
        enable_clustering=False,
        confidence_warnings=False,
    ),
    ScoringTier.FULL: TierThresholds(
        min_notes=50000,
        max_notes=None,
        description="Full tier: Complete pipeline with clustering (50000+ notes)",
        scorers=[
            "MFCoreScorer",
            "MFExpansionScorer",
            "MFGroupScorer",
            "MFExpansionPlusScorer",
        ],
        requires_full_pipeline=True,
        enable_clustering=True,
        confidence_warnings=False,
    ),
}


def get_tier_for_note_count(note_count: int) -> ScoringTier:
    if note_count < 200:
        return ScoringTier.MINIMAL
    if note_count < 1000:
        return ScoringTier.LIMITED
    if note_count < 5000:
        return ScoringTier.BASIC
    if note_count < 10000:
        return ScoringTier.INTERMEDIATE
    if note_count < 50000:
        return ScoringTier.ADVANCED
    return ScoringTier.FULL


def get_tier_config(tier: ScoringTier) -> TierThresholds:
    return TIER_CONFIGURATIONS[tier]
