from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.content_moderation_classification_result_category_labels import (
        ContentModerationClassificationResultCategoryLabels,
    )
    from ..models.content_moderation_classification_result_category_scores_type_0 import (
        ContentModerationClassificationResultCategoryScoresType0,
    )


T = TypeVar("T", bound="ContentModerationClassificationResult")


@_attrs_define
class ContentModerationClassificationResult:
    """Structured output from the ContentReviewerAgent.

    Contains the agent's classification decision: confidence, category labels,
    recommended action, action tier, and explanation. Added to MatchResult
    union alongside existing match types.

        Attributes:
            confidence (float): Classification confidence score
            category_labels (ContentModerationClassificationResultCategoryLabels): Category labels with flagged/not-flagged
                status
            explanation (str): Human-readable explanation of the classification
            scan_type (Literal['content_moderation_classification'] | Unset):  Default: 'content_moderation_classification'.
            category_scores (ContentModerationClassificationResultCategoryScoresType0 | None | Unset): Per-category
                confidence scores
            recommended_action (None | str | Unset): Recommended action (hide, review, pass)
            action_tier (None | str | Unset): Action tier (tier_1_immediate, tier_2_consensus)
    """

    confidence: float
    category_labels: ContentModerationClassificationResultCategoryLabels
    explanation: str
    scan_type: Literal["content_moderation_classification"] | Unset = (
        "content_moderation_classification"
    )
    category_scores: (
        ContentModerationClassificationResultCategoryScoresType0 | None | Unset
    ) = UNSET
    recommended_action: None | str | Unset = UNSET
    action_tier: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.content_moderation_classification_result_category_scores_type_0 import (
            ContentModerationClassificationResultCategoryScoresType0,
        )

        confidence = self.confidence

        category_labels = self.category_labels.to_dict()

        explanation = self.explanation

        scan_type = self.scan_type

        category_scores: dict[str, Any] | None | Unset
        if isinstance(self.category_scores, Unset):
            category_scores = UNSET
        elif isinstance(
            self.category_scores,
            ContentModerationClassificationResultCategoryScoresType0,
        ):
            category_scores = self.category_scores.to_dict()
        else:
            category_scores = self.category_scores

        recommended_action: None | str | Unset
        if isinstance(self.recommended_action, Unset):
            recommended_action = UNSET
        else:
            recommended_action = self.recommended_action

        action_tier: None | str | Unset
        if isinstance(self.action_tier, Unset):
            action_tier = UNSET
        else:
            action_tier = self.action_tier

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "confidence": confidence,
                "category_labels": category_labels,
                "explanation": explanation,
            }
        )
        if scan_type is not UNSET:
            field_dict["scan_type"] = scan_type
        if category_scores is not UNSET:
            field_dict["category_scores"] = category_scores
        if recommended_action is not UNSET:
            field_dict["recommended_action"] = recommended_action
        if action_tier is not UNSET:
            field_dict["action_tier"] = action_tier

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.content_moderation_classification_result_category_labels import (
            ContentModerationClassificationResultCategoryLabels,
        )
        from ..models.content_moderation_classification_result_category_scores_type_0 import (
            ContentModerationClassificationResultCategoryScoresType0,
        )

        d = dict(src_dict)
        confidence = d.pop("confidence")

        category_labels = ContentModerationClassificationResultCategoryLabels.from_dict(
            d.pop("category_labels")
        )

        explanation = d.pop("explanation")

        scan_type = cast(
            Literal["content_moderation_classification"] | Unset,
            d.pop("scan_type", UNSET),
        )
        if scan_type != "content_moderation_classification" and not isinstance(
            scan_type, Unset
        ):
            raise ValueError(
                f"scan_type must match const 'content_moderation_classification', got '{scan_type}'"
            )

        def _parse_category_scores(
            data: object,
        ) -> ContentModerationClassificationResultCategoryScoresType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                category_scores_type_0 = (
                    ContentModerationClassificationResultCategoryScoresType0.from_dict(
                        data
                    )
                )

                return category_scores_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                ContentModerationClassificationResultCategoryScoresType0 | None | Unset,
                data,
            )

        category_scores = _parse_category_scores(d.pop("category_scores", UNSET))

        def _parse_recommended_action(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        recommended_action = _parse_recommended_action(
            d.pop("recommended_action", UNSET)
        )

        def _parse_action_tier(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        action_tier = _parse_action_tier(d.pop("action_tier", UNSET))

        content_moderation_classification_result = cls(
            confidence=confidence,
            category_labels=category_labels,
            explanation=explanation,
            scan_type=scan_type,
            category_scores=category_scores,
            recommended_action=recommended_action,
            action_tier=action_tier,
        )

        return content_moderation_classification_result
