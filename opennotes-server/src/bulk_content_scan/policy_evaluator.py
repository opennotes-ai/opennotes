"""Deterministic policy layer for mapping classification results to moderation action decisions."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.bulk_content_scan.schemas import ContentModerationClassificationResult
from src.moderation_actions.models import ActionTier, ActionType, ReviewGroup

_REVIEW_GROUP_PRIORITY: dict[str, int] = {
    ReviewGroup.STAFF: 3,
    ReviewGroup.TRUSTED: 2,
    ReviewGroup.COMMUNITY: 1,
}

_REVIEW_GROUP_BY_NAME: dict[str, ReviewGroup] = {
    "staff": ReviewGroup.STAFF,
    "trusted": ReviewGroup.TRUSTED,
    "community": ReviewGroup.COMMUNITY,
}


@dataclass
class ModerationPolicyConfig:
    """Per-community configuration for moderation policy thresholds and routing."""

    auto_action_labels: list[str] = field(default_factory=list)
    auto_action_min_score: float = 0.90
    review_labels: list[str] = field(default_factory=lambda: ["*"])
    review_min_score: float = 0.50
    label_routing: dict[str, list[str]] = field(default_factory=lambda: {"staff": ["*"]})


@dataclass
class PolicyDecision:
    """Result of applying policy config to a classification result."""

    action_tier: ActionTier | None
    action_type: ActionType | None
    review_group: ReviewGroup | None
    reason: str


class ModerationPolicyEvaluator:
    """Evaluates a ContentModerationClassificationResult against a ModerationPolicyConfig.

    Pure deterministic logic — no async, no DB, no I/O. The policy config is
    authoritative; any agent recommendation is treated as advisory only.

    Evaluation order (highest severity first):
      1. Tier 1 (immediate) — label in auto_action_labels AND score >= auto_action_min_score
      2. Tier 2 (consensus) — label in review_labels (or wildcard "*") AND score >= review_min_score
      3. Pass — no configured threshold was exceeded
    """

    def evaluate(
        self,
        classification: ContentModerationClassificationResult,
        config: ModerationPolicyConfig,
    ) -> PolicyDecision:
        if classification.error_type is not None:
            return PolicyDecision(
                action_tier=None,
                action_type=None,
                review_group=None,
                reason=f"Classification failed: {classification.error_type}",
            )

        flagged_labels = [
            label for label, flagged in classification.category_labels.items() if flagged
        ]

        tier1_labels = self._tier1_labels(flagged_labels, classification, config)
        if tier1_labels:
            triggering_label = tier1_labels[0]
            review_group = self._resolve_review_group(tier1_labels, config)
            return PolicyDecision(
                action_tier=ActionTier.TIER_1_IMMEDIATE,
                action_type=ActionType.HIDE,
                review_group=review_group,
                reason=f"Tier 1 auto-action triggered by label '{triggering_label}'",
            )

        tier2_labels = self._tier2_labels(flagged_labels, classification, config)
        if tier2_labels:
            triggering_label = tier2_labels[0]
            review_group = self._resolve_review_group(tier2_labels, config)
            return PolicyDecision(
                action_tier=ActionTier.TIER_2_CONSENSUS,
                action_type=ActionType.HIDE,
                review_group=review_group,
                reason=f"Tier 2 consensus review triggered by label '{triggering_label}'",
            )

        return PolicyDecision(
            action_tier=None,
            action_type=None,
            review_group=None,
            reason="No configured threshold exceeded; no action required",
        )

    def _get_score(
        self,
        label: str,
        classification: ContentModerationClassificationResult,
    ) -> float:
        if classification.category_scores and label in classification.category_scores:
            return classification.category_scores[label]
        return classification.confidence

    def _tier1_labels(
        self,
        flagged_labels: list[str],
        classification: ContentModerationClassificationResult,
        config: ModerationPolicyConfig,
    ) -> list[str]:
        if not config.auto_action_labels:
            return []
        result = []
        for label in flagged_labels:
            if label in config.auto_action_labels:
                score = self._get_score(label, classification)
                if score >= config.auto_action_min_score:
                    result.append(label)
        return result

    def _tier2_labels(
        self,
        flagged_labels: list[str],
        classification: ContentModerationClassificationResult,
        config: ModerationPolicyConfig,
    ) -> list[str]:
        if not config.review_labels:
            return []
        has_wildcard = "*" in config.review_labels
        result = []
        for label in flagged_labels:
            if has_wildcard or label in config.review_labels:
                score = self._get_score(label, classification)
                if score >= config.review_min_score:
                    result.append(label)
        return result

    def _resolve_review_group(
        self,
        triggered_labels: list[str],
        config: ModerationPolicyConfig,
    ) -> ReviewGroup:
        best_group: ReviewGroup = ReviewGroup.COMMUNITY
        best_priority: int = 0

        for group_name, routed_labels in config.label_routing.items():
            group = _REVIEW_GROUP_BY_NAME.get(group_name)
            if group is None:
                continue
            priority = _REVIEW_GROUP_PRIORITY.get(group, 0)
            has_wildcard = "*" in routed_labels
            for label in triggered_labels:
                if has_wildcard or label in routed_labels:
                    if priority > best_priority:
                        best_priority = priority
                        best_group = group
                    break

        return best_group
