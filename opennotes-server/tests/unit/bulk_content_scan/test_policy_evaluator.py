"""Tests for ModerationPolicyEvaluator - TDD implementation."""

from src.bulk_content_scan.schemas import ContentModerationClassificationResult
from src.moderation_actions.models import ActionTier, ActionType, ReviewGroup


class TestModerationPolicyConfig:
    """Tests for ModerationPolicyConfig dataclass defaults."""

    def test_default_config_has_empty_auto_action_labels(self):
        from src.bulk_content_scan.policy_evaluator import ModerationPolicyConfig

        config = ModerationPolicyConfig()
        assert config.auto_action_labels == []

    def test_default_auto_action_min_score_is_0_90(self):
        from src.bulk_content_scan.policy_evaluator import ModerationPolicyConfig

        config = ModerationPolicyConfig()
        assert config.auto_action_min_score == 0.90

    def test_default_review_labels_is_wildcard(self):
        from src.bulk_content_scan.policy_evaluator import ModerationPolicyConfig

        config = ModerationPolicyConfig()
        assert config.review_labels == ["*"]

    def test_default_review_min_score_is_0_50(self):
        from src.bulk_content_scan.policy_evaluator import ModerationPolicyConfig

        config = ModerationPolicyConfig()
        assert config.review_min_score == 0.50

    def test_default_label_routing_maps_staff_to_wildcard(self):
        from src.bulk_content_scan.policy_evaluator import ModerationPolicyConfig

        config = ModerationPolicyConfig()
        assert config.label_routing == {"staff": ["*"]}

    def test_can_override_all_fields(self):
        from src.bulk_content_scan.policy_evaluator import ModerationPolicyConfig

        config = ModerationPolicyConfig(
            auto_action_labels=["harassment", "spam"],
            auto_action_min_score=0.85,
            review_labels=["misinformation"],
            review_min_score=0.60,
            label_routing={"trusted": ["misinformation"], "staff": ["harassment"]},
        )
        assert config.auto_action_labels == ["harassment", "spam"]
        assert config.auto_action_min_score == 0.85
        assert config.review_labels == ["misinformation"]
        assert config.review_min_score == 0.60
        assert config.label_routing == {
            "trusted": ["misinformation"],
            "staff": ["harassment"],
        }


class TestPolicyDecision:
    """Tests for PolicyDecision dataclass."""

    def test_can_construct_tier1_decision(self):
        from src.bulk_content_scan.policy_evaluator import PolicyDecision

        decision = PolicyDecision(
            action_tier=ActionTier.TIER_1_IMMEDIATE,
            action_type=ActionType.HIDE,
            review_group=ReviewGroup.STAFF,
            reason="harassment label triggered auto-action",
        )
        assert decision.action_tier == ActionTier.TIER_1_IMMEDIATE
        assert decision.action_type == ActionType.HIDE
        assert decision.review_group == ReviewGroup.STAFF

    def test_can_construct_pass_decision(self):
        from src.bulk_content_scan.policy_evaluator import PolicyDecision

        decision = PolicyDecision(
            action_tier=None,
            action_type=None,
            review_group=None,
            reason="no labels exceeded thresholds",
        )
        assert decision.action_tier is None
        assert decision.action_type is None
        assert decision.review_group is None


class TestModerationPolicyEvaluatorTier1:
    """Tests for Tier 1 (immediate) action triggering."""

    def _make_classification(
        self,
        category_labels: dict[str, bool],
        category_scores: dict[str, float] | None = None,
        recommended_action: str | None = None,
        action_tier: str | None = None,
        confidence: float = 0.95,
        explanation: str = "test explanation",
    ) -> ContentModerationClassificationResult:
        return ContentModerationClassificationResult(
            confidence=confidence,
            category_labels=category_labels,
            category_scores=category_scores,
            recommended_action=recommended_action,
            action_tier=action_tier,
            explanation=explanation,
        )

    def test_tier1_triggered_when_label_in_auto_action_labels_and_score_meets_threshold(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.95},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier == ActionTier.TIER_1_IMMEDIATE
        assert decision.action_type == ActionType.HIDE

    def test_tier1_not_triggered_when_score_below_threshold(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
            review_labels=[],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.85},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier != ActionTier.TIER_1_IMMEDIATE

    def test_tier1_not_triggered_when_label_not_in_auto_action_labels(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["spam"],
            auto_action_min_score=0.90,
            review_labels=[],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.95},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier != ActionTier.TIER_1_IMMEDIATE

    def test_tier1_not_triggered_when_label_is_false(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
        )
        classification = self._make_classification(
            category_labels={"harassment": False},
            category_scores={"harassment": 0.95},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier != ActionTier.TIER_1_IMMEDIATE

    def test_tier1_uses_confidence_when_category_scores_absent(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores=None,
            confidence=0.95,
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier == ActionTier.TIER_1_IMMEDIATE

    def test_tier1_default_action_type_is_hide(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.95},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_type == ActionType.HIDE


class TestModerationPolicyEvaluatorTier2:
    """Tests for Tier 2 (consensus) action triggering."""

    def _make_classification(
        self,
        category_labels: dict[str, bool],
        category_scores: dict[str, float] | None = None,
        confidence: float = 0.70,
        explanation: str = "test explanation",
    ) -> ContentModerationClassificationResult:
        return ContentModerationClassificationResult(
            confidence=confidence,
            category_labels=category_labels,
            category_scores=category_scores,
            explanation=explanation,
        )

    def test_tier2_triggered_when_label_in_review_labels_and_score_meets_threshold(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=["misinformation"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"misinformation": True},
            category_scores={"misinformation": 0.60},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier == ActionTier.TIER_2_CONSENSUS
        assert decision.action_type == ActionType.HIDE

    def test_tier2_not_triggered_when_score_below_threshold(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=["misinformation"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"misinformation": True},
            category_scores={"misinformation": 0.40},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier is None

    def test_tier2_wildcard_matches_any_true_label(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=["*"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"some_random_label": True},
            category_scores={"some_random_label": 0.60},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier == ActionTier.TIER_2_CONSENSUS

    def test_tier2_wildcard_requires_score_threshold(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=["*"],
            review_min_score=0.70,
        )
        classification = self._make_classification(
            category_labels={"some_random_label": True},
            category_scores={"some_random_label": 0.60},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier is None

    def test_tier2_uses_confidence_when_category_scores_absent(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=["misinformation"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"misinformation": True},
            category_scores=None,
            confidence=0.70,
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier == ActionTier.TIER_2_CONSENSUS


class TestModerationPolicyEvaluatorPass:
    """Tests for pass (no action) decision."""

    def _make_classification(
        self,
        category_labels: dict[str, bool],
        category_scores: dict[str, float] | None = None,
        confidence: float = 0.40,
        explanation: str = "test explanation",
    ) -> ContentModerationClassificationResult:
        return ContentModerationClassificationResult(
            confidence=confidence,
            category_labels=category_labels,
            category_scores=category_scores,
            explanation=explanation,
        )

    def test_pass_when_no_labels_flagged(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            review_labels=["*"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"harassment": False, "misinformation": False},
            category_scores={"harassment": 0.10, "misinformation": 0.20},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier is None
        assert decision.action_type is None
        assert decision.review_group is None

    def test_pass_when_empty_category_labels(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig()
        classification = self._make_classification(
            category_labels={},
            confidence=0.30,
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier is None

    def test_pass_decision_has_reason(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=[],
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.95},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier is None
        assert isinstance(decision.reason, str)
        assert len(decision.reason) > 0


class TestModerationPolicyEvaluatorVeto:
    """Tests for policy veto/downgrade of agent recommendations."""

    def _make_classification(
        self,
        category_labels: dict[str, bool],
        category_scores: dict[str, float] | None = None,
        recommended_action: str | None = "hide",
        action_tier: str | None = "tier_1_immediate",
        confidence: float = 0.95,
        explanation: str = "agent flagged as tier 1",
    ) -> ContentModerationClassificationResult:
        return ContentModerationClassificationResult(
            confidence=confidence,
            category_labels=category_labels,
            category_scores=category_scores,
            recommended_action=recommended_action,
            action_tier=action_tier,
            explanation=explanation,
        )

    def test_veto_agent_tier1_when_auto_action_labels_empty(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=["harassment"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.95},
            recommended_action="hide",
            action_tier="tier_1_immediate",
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier != ActionTier.TIER_1_IMMEDIATE
        assert decision.action_tier == ActionTier.TIER_2_CONSENSUS

    def test_veto_agent_tier1_to_pass_when_no_labels_configured(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=[],
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.95},
            recommended_action="hide",
            action_tier="tier_1_immediate",
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier is None

    def test_agent_recommendation_is_advisory_only(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
            review_labels=[],
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.95},
            recommended_action="pass",
            action_tier=None,
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier == ActionTier.TIER_1_IMMEDIATE


class TestModerationPolicyEvaluatorLabelRouting:
    """Tests for label_routing -> review_group resolution."""

    def _make_classification(
        self,
        category_labels: dict[str, bool],
        category_scores: dict[str, float] | None = None,
        confidence: float = 0.70,
        explanation: str = "test",
    ) -> ContentModerationClassificationResult:
        return ContentModerationClassificationResult(
            confidence=confidence,
            category_labels=category_labels,
            category_scores=category_scores,
            explanation=explanation,
        )

    def test_label_routing_maps_label_to_staff(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=["harassment"],
            review_min_score=0.50,
            label_routing={"staff": ["harassment"]},
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.70},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.review_group == ReviewGroup.STAFF

    def test_label_routing_maps_label_to_trusted(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=["misinformation"],
            review_min_score=0.50,
            label_routing={"trusted": ["misinformation"]},
        )
        classification = self._make_classification(
            category_labels={"misinformation": True},
            category_scores={"misinformation": 0.70},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.review_group == ReviewGroup.TRUSTED

    def test_label_routing_wildcard_routes_to_staff(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=["*"],
            review_min_score=0.50,
            label_routing={"staff": ["*"]},
        )
        classification = self._make_classification(
            category_labels={"any_label": True},
            category_scores={"any_label": 0.70},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.review_group == ReviewGroup.STAFF

    def test_label_routing_defaults_to_community_when_no_match(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=[],
            review_labels=["misinformation"],
            review_min_score=0.50,
            label_routing={},
        )
        classification = self._make_classification(
            category_labels={"misinformation": True},
            category_scores={"misinformation": 0.70},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.review_group == ReviewGroup.COMMUNITY


class TestModerationPolicyEvaluatorMultiLabel:
    """Tests for multi-label precedence rules."""

    def _make_classification(
        self,
        category_labels: dict[str, bool],
        category_scores: dict[str, float] | None = None,
        confidence: float = 0.80,
        explanation: str = "test",
    ) -> ContentModerationClassificationResult:
        return ContentModerationClassificationResult(
            confidence=confidence,
            category_labels=category_labels,
            category_scores=category_scores,
            explanation=explanation,
        )

    def test_tier1_wins_over_tier2_when_both_labels_present(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
            review_labels=["misinformation"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"harassment": True, "misinformation": True},
            category_scores={"harassment": 0.95, "misinformation": 0.60},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier == ActionTier.TIER_1_IMMEDIATE

    def test_tier2_when_only_tier2_label_present(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
            review_labels=["misinformation"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"harassment": False, "misinformation": True},
            category_scores={"harassment": 0.30, "misinformation": 0.60},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier == ActionTier.TIER_2_CONSENSUS

    def test_pass_when_tier1_label_present_but_tier2_label_absent(self):
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
            review_labels=["misinformation"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"harassment": False, "misinformation": False},
            category_scores={"harassment": 0.30, "misinformation": 0.30},
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier is None


class TestModerationPolicyEvaluatorErrorTypeSkip:
    """AC2: Policy evaluator skips evaluation when error_type is set."""

    def _make_classification(
        self,
        category_labels: dict[str, bool],
        category_scores: dict[str, float] | None = None,
        confidence: float = 0.0,
        explanation: str = "Classification failed",
        error_type: str | None = None,
    ) -> ContentModerationClassificationResult:
        return ContentModerationClassificationResult(
            confidence=confidence,
            category_labels=category_labels,
            category_scores=category_scores,
            explanation=explanation,
            error_type=error_type,
        )

    def test_evaluator_returns_pass_when_error_type_is_set(self):
        """evaluate() should skip policy evaluation and return pass when error_type is set."""
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
            review_labels=["*"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={},
            error_type="timeout",
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier is None
        assert decision.action_type is None
        assert decision.review_group is None

    def test_evaluator_reason_includes_error_type_when_set(self):
        """evaluate() reason should include the error_type string when error occurred."""
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig()
        classification = self._make_classification(
            category_labels={},
            error_type="transport_error",
        )

        decision = evaluator.evaluate(classification, config)

        assert "transport_error" in decision.reason

    def test_evaluator_skips_for_all_error_types(self):
        """evaluate() should skip for all error_type values: timeout, transport_error, parse_error, unexpected_error."""
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
            review_labels=["*"],
            review_min_score=0.50,
        )

        for error_type in ("timeout", "transport_error", "parse_error", "unexpected_error"):
            classification = self._make_classification(
                category_labels={"harassment": True},
                category_scores={"harassment": 0.99},
                error_type=error_type,
            )
            decision = evaluator.evaluate(classification, config)
            assert decision.action_tier is None, f"Expected pass for error_type={error_type!r}"

    def test_evaluator_proceeds_normally_when_error_type_is_none(self):
        """evaluate() should run normal policy evaluation when error_type is None."""
        from src.bulk_content_scan.policy_evaluator import (
            ModerationPolicyConfig,
            ModerationPolicyEvaluator,
        )

        evaluator = ModerationPolicyEvaluator()
        config = ModerationPolicyConfig(
            auto_action_labels=["harassment"],
            auto_action_min_score=0.90,
            review_labels=["*"],
            review_min_score=0.50,
        )
        classification = self._make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.95},
            confidence=0.95,
            error_type=None,
        )

        decision = evaluator.evaluate(classification, config)

        assert decision.action_tier == ActionTier.TIER_1_IMMEDIATE
