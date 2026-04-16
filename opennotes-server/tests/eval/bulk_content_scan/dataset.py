"""Curated eval dataset for the ContentReviewerAgent offline regression harness.

Each EvalCase captures a (content_item, evidence, expected_outcome) triple.
The dataset covers all action/tier combinations and edge cases:
  - Clear misinformation + high similarity  → hide / tier_1_immediate
  - Mild benign content + no evidence       → pass / None
  - Hate speech flagged by moderation       → hide / tier_1_immediate
  - Flashpoint escalation                   → review / tier_2_consensus
  - Low-confidence ambiguous content        → pass or review
  - Retry-recovery case (output_validator)  → review / tier_2_consensus
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pendulum

from src.bulk_content_scan.schemas import (
    ContentItem,
    ContentModerationClassificationResult,
    ConversationFlashpointMatch,
    OpenAIModerationMatch,
    RiskLevel,
    SimilarityMatch,
)


@dataclass
class EvalCase:
    name: str
    content_item: ContentItem
    evidence: list[SimilarityMatch | OpenAIModerationMatch | ConversationFlashpointMatch]
    expected_action: str | None
    expected_tier: str | None
    expected_confidence_range: tuple[float, float]
    description: str = ""
    requires_retry_recovery: bool = False


def _make_content_item(
    content_id: str,
    content_text: str,
    platform: str = "discord",
    channel_id: str = "ch_eval",
    community_server_id: str = "server_eval",
) -> ContentItem:
    return ContentItem(
        content_id=content_id,
        platform=platform,
        content_text=content_text,
        author_id=f"author_{content_id}",
        author_username=f"user_{content_id}",
        timestamp=pendulum.datetime(2024, 1, 15, 12, 0, 0, tz="UTC"),
        channel_id=channel_id,
        community_server_id=community_server_id,
    )


def _make_similarity_match(
    score: float,
    matched_claim: str,
    matched_source: str = "https://example.com/fact-check",
    fact_check_item_id: UUID | None = None,
) -> SimilarityMatch:
    if fact_check_item_id is None:
        fact_check_item_id = UUID("00000000-0000-0000-0000-000000000001")
    return SimilarityMatch(
        score=score,
        matched_claim=matched_claim,
        matched_source=matched_source,
        fact_check_item_id=fact_check_item_id,
    )


def _make_moderation_match(
    max_score: float,
    flagged_categories: list[str],
) -> OpenAIModerationMatch:
    categories = dict.fromkeys(flagged_categories, True)
    scores = dict.fromkeys(flagged_categories, max_score)
    return OpenAIModerationMatch(
        max_score=max_score,
        categories=categories,
        scores=scores,
        flagged_categories=flagged_categories,
    )


def _make_flashpoint_match(
    derailment_score: int,
    risk_level: RiskLevel,
    reasoning: str,
    context_messages: int = 3,
) -> ConversationFlashpointMatch:
    return ConversationFlashpointMatch(
        derailment_score=derailment_score,
        risk_level=risk_level,
        reasoning=reasoning,
        context_messages=context_messages,
    )


EVAL_DATASET: list[EvalCase] = [
    EvalCase(
        name="clear_misinformation_high_similarity",
        description="Vaccine misinformation with high-confidence similarity match → immediate hide",
        content_item=_make_content_item(
            "eval_001",
            "Vaccines cause autism, it's been proven by multiple independent studies. "
            "The CDC is hiding this information from the public.",
        ),
        evidence=[
            _make_similarity_match(
                score=0.94,
                matched_claim="Vaccines do not cause autism; this claim has been debunked by "
                "extensive peer-reviewed research",
                matched_source="https://cdc.gov/vaccinesafety/concerns/autism.html",
                fact_check_item_id=UUID("00000000-0000-0000-0000-000000000001"),
            )
        ],
        expected_action="hide",
        expected_tier="tier_1_immediate",
        expected_confidence_range=(0.80, 1.0),
    ),
    EvalCase(
        name="benign_content_no_evidence",
        description="Ordinary discussion with no evidence signals → pass with no tier",
        content_item=_make_content_item(
            "eval_002",
            "I really enjoyed the new movie that came out last week. The CGI was impressive "
            "and the story was well-written.",
        ),
        evidence=[],
        expected_action="pass",
        expected_tier=None,
        expected_confidence_range=(0.60, 1.0),
    ),
    EvalCase(
        name="hate_speech_moderation_flag",
        description="Direct hate speech flagged by OpenAI moderation at high score → hide tier_1",
        content_item=_make_content_item(
            "eval_003",
            "All people from that group should be removed from our community. "
            "They are inferior and don't belong here.",
        ),
        evidence=[
            _make_moderation_match(
                max_score=0.93,
                flagged_categories=["hate", "hate/threatening"],
            )
        ],
        expected_action="hide",
        expected_tier="tier_1_immediate",
        expected_confidence_range=(0.80, 1.0),
    ),
    EvalCase(
        name="flashpoint_escalation_tier2",
        description="Heated conversation flashpoint → review escalated to tier_2_consensus",
        content_item=_make_content_item(
            "eval_004",
            "You clearly have no idea what you're talking about. Stop spreading your garbage "
            "opinions in this server.",
        ),
        evidence=[
            _make_flashpoint_match(
                derailment_score=72,
                risk_level=RiskLevel.HEATED,
                reasoning="Sustained personal attacks and dismissive language escalating conflict",
                context_messages=5,
            )
        ],
        expected_action="review",
        expected_tier="tier_2_consensus",
        expected_confidence_range=(0.65, 1.0),
    ),
    EvalCase(
        name="low_confidence_ambiguous",
        description="Borderline content with weak similarity signal → pass or review with low confidence",
        content_item=_make_content_item(
            "eval_005",
            "Some researchers suggest that electromagnetic fields from phones might have "
            "minor effects on sleep quality.",
        ),
        evidence=[
            _make_similarity_match(
                score=0.42,
                matched_claim="5G networks cause health problems",
                matched_source="https://example.com/emf-fact-check",
                fact_check_item_id=UUID("00000000-0000-0000-0000-000000000002"),
            )
        ],
        expected_action=None,
        expected_tier=None,
        expected_confidence_range=(0.0, 0.70),
    ),
    EvalCase(
        name="mixed_evidence_similarity_and_moderation",
        description="Both similarity match and moderation signal → hide tier_1 with high confidence",
        content_item=_make_content_item(
            "eval_006",
            "This [slur] group is responsible for all economic problems. The data clearly shows "
            "they control the media and financial institutions.",
        ),
        evidence=[
            _make_similarity_match(
                score=0.78,
                matched_claim="Antisemitic conspiracy theory: Jewish people control media/finance",
                matched_source="https://example.com/antisemitism-fact-check",
                fact_check_item_id=UUID("00000000-0000-0000-0000-000000000003"),
            ),
            _make_moderation_match(
                max_score=0.88,
                flagged_categories=["hate"],
            ),
        ],
        expected_action="hide",
        expected_tier="tier_1_immediate",
        expected_confidence_range=(0.85, 1.0),
    ),
    EvalCase(
        name="hostile_flashpoint_escalation",
        description="Hostile derailment score with threatening undertones → hide or review tier_1",
        content_item=_make_content_item(
            "eval_007",
            "I know where you live and you'll regret posting this. Watch yourself.",
        ),
        evidence=[
            _make_flashpoint_match(
                derailment_score=91,
                risk_level=RiskLevel.HOSTILE,
                reasoning="Explicit threat pattern detected with personal targeting language",
                context_messages=4,
            )
        ],
        expected_action="hide",
        expected_tier="tier_1_immediate",
        expected_confidence_range=(0.80, 1.0),
    ),
    EvalCase(
        name="retry_recovery_case",
        description=(
            "Output validator rejects first attempt; second attempt returns correct result. "
            "Tests that retry budget is properly consumed and final answer is accepted."
        ),
        content_item=_make_content_item(
            "eval_008",
            "The earth is flat and NASA has been lying to us for decades. "
            "Photos of the round earth are CGI composites.",
        ),
        evidence=[
            _make_similarity_match(
                score=0.89,
                matched_claim="The Earth is an oblate spheroid; flat-earth claims are false",
                matched_source="https://nasa.gov/earth-shape",
                fact_check_item_id=UUID("00000000-0000-0000-0000-000000000004"),
            )
        ],
        expected_action="review",
        expected_tier="tier_2_consensus",
        expected_confidence_range=(0.70, 1.0),
        requires_retry_recovery=True,
    ),
    EvalCase(
        name="guarded_flashpoint_low_threshold",
        description="Guarded flashpoint only, no other evidence → review tier_2 at lower confidence",
        content_item=_make_content_item(
            "eval_009",
            "I disagree with your point. This argument has been going on long enough.",
        ),
        evidence=[
            _make_flashpoint_match(
                derailment_score=35,
                risk_level=RiskLevel.GUARDED,
                reasoning="Minor tension and repeated disagreement without resolution",
                context_messages=6,
            )
        ],
        expected_action="review",
        expected_tier="tier_2_consensus",
        expected_confidence_range=(0.50, 0.90),
    ),
    EvalCase(
        name="discourse_platform_content",
        description="Non-Discord platform (Discourse) is handled correctly → pass/None",
        content_item=_make_content_item(
            "eval_010",
            "Has anyone tried the new restaurant downtown? The reviews seem mixed.",
            platform="discourse",
        ),
        evidence=[],
        expected_action="pass",
        expected_tier=None,
        expected_confidence_range=(0.60, 1.0),
    ),
]


def get_standard_cases() -> list[EvalCase]:
    return [c for c in EVAL_DATASET if not c.requires_retry_recovery]


def get_retry_recovery_cases() -> list[EvalCase]:
    return [c for c in EVAL_DATASET if c.requires_retry_recovery]


def build_expected_result(
    case: EvalCase,
    action: str | None = None,
    tier: str | None = None,
    confidence: float | None = None,
) -> ContentModerationClassificationResult:
    resolved_action = action if action is not None else case.expected_action
    resolved_tier = tier if tier is not None else case.expected_tier
    resolved_confidence = (
        confidence
        if confidence is not None
        else ((case.expected_confidence_range[0] + case.expected_confidence_range[1]) / 2)
    )
    return ContentModerationClassificationResult(
        confidence=resolved_confidence,
        category_labels={"flagged": resolved_action in ("hide", "review")},
        recommended_action=resolved_action,
        action_tier=resolved_tier,
        explanation=f"Eval harness result for case: {case.name}",
    )
