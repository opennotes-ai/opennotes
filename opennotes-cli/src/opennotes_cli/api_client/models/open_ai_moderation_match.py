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
    from ..models.open_ai_moderation_match_categories import (
        OpenAIModerationMatchCategories,
    )
    from ..models.open_ai_moderation_match_scores import OpenAIModerationMatchScores


T = TypeVar("T", bound="OpenAIModerationMatch")


@_attrs_define
class OpenAIModerationMatch:
    """Match result from OpenAI moderation scan.

    Attributes:
        max_score (float): Max moderation score
        categories (OpenAIModerationMatchCategories): Moderation categories
        scores (OpenAIModerationMatchScores): Category scores
        scan_type (Literal['openai_moderation'] | Unset):  Default: 'openai_moderation'.
        flagged_categories (list[str] | Unset): Flagged category names
    """

    max_score: float
    categories: OpenAIModerationMatchCategories
    scores: OpenAIModerationMatchScores
    scan_type: Literal["openai_moderation"] | Unset = "openai_moderation"
    flagged_categories: list[str] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        max_score = self.max_score

        categories = self.categories.to_dict()

        scores = self.scores.to_dict()

        scan_type = self.scan_type

        flagged_categories: list[str] | Unset = UNSET
        if not isinstance(self.flagged_categories, Unset):
            flagged_categories = self.flagged_categories

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "max_score": max_score,
                "categories": categories,
                "scores": scores,
            }
        )
        if scan_type is not UNSET:
            field_dict["scan_type"] = scan_type
        if flagged_categories is not UNSET:
            field_dict["flagged_categories"] = flagged_categories

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.open_ai_moderation_match_categories import (
            OpenAIModerationMatchCategories,
        )
        from ..models.open_ai_moderation_match_scores import OpenAIModerationMatchScores

        d = dict(src_dict)
        max_score = d.pop("max_score")

        categories = OpenAIModerationMatchCategories.from_dict(d.pop("categories"))

        scores = OpenAIModerationMatchScores.from_dict(d.pop("scores"))

        scan_type = cast(
            Literal["openai_moderation"] | Unset, d.pop("scan_type", UNSET)
        )
        if scan_type != "openai_moderation" and not isinstance(scan_type, Unset):
            raise ValueError(
                f"scan_type must match const 'openai_moderation', got '{scan_type}'"
            )

        flagged_categories = cast(list[str], d.pop("flagged_categories", UNSET))

        open_ai_moderation_match = cls(
            max_score=max_score,
            categories=categories,
            scores=scores,
            scan_type=scan_type,
            flagged_categories=flagged_categories,
        )

        return open_ai_moderation_match
