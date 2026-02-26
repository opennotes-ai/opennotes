from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.scoring_result_attributes_auxiliary_info_item import (
        ScoringResultAttributesAuxiliaryInfoItem,
    )
    from ..models.scoring_result_attributes_helpful_scores_item import (
        ScoringResultAttributesHelpfulScoresItem,
    )
    from ..models.scoring_result_attributes_scored_notes_item import (
        ScoringResultAttributesScoredNotesItem,
    )


T = TypeVar("T", bound="ScoringResultAttributes")


@_attrs_define
class ScoringResultAttributes:
    """Attributes for scoring result resource.

    Attributes:
        scored_notes (list[ScoringResultAttributesScoredNotesItem]): Scored notes output from the algorithm
        helpful_scores (list[ScoringResultAttributesHelpfulScoresItem]): Helpful scores for raters
        auxiliary_info (list[ScoringResultAttributesAuxiliaryInfoItem]): Auxiliary information from scoring
    """

    scored_notes: list[ScoringResultAttributesScoredNotesItem]
    helpful_scores: list[ScoringResultAttributesHelpfulScoresItem]
    auxiliary_info: list[ScoringResultAttributesAuxiliaryInfoItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        scored_notes = []
        for scored_notes_item_data in self.scored_notes:
            scored_notes_item = scored_notes_item_data.to_dict()
            scored_notes.append(scored_notes_item)

        helpful_scores = []
        for helpful_scores_item_data in self.helpful_scores:
            helpful_scores_item = helpful_scores_item_data.to_dict()
            helpful_scores.append(helpful_scores_item)

        auxiliary_info = []
        for auxiliary_info_item_data in self.auxiliary_info:
            auxiliary_info_item = auxiliary_info_item_data.to_dict()
            auxiliary_info.append(auxiliary_info_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "scored_notes": scored_notes,
                "helpful_scores": helpful_scores,
                "auxiliary_info": auxiliary_info,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.scoring_result_attributes_auxiliary_info_item import (
            ScoringResultAttributesAuxiliaryInfoItem,
        )
        from ..models.scoring_result_attributes_helpful_scores_item import (
            ScoringResultAttributesHelpfulScoresItem,
        )
        from ..models.scoring_result_attributes_scored_notes_item import (
            ScoringResultAttributesScoredNotesItem,
        )

        d = dict(src_dict)
        scored_notes = []
        _scored_notes = d.pop("scored_notes")
        for scored_notes_item_data in _scored_notes:
            scored_notes_item = ScoringResultAttributesScoredNotesItem.from_dict(
                scored_notes_item_data
            )

            scored_notes.append(scored_notes_item)

        helpful_scores = []
        _helpful_scores = d.pop("helpful_scores")
        for helpful_scores_item_data in _helpful_scores:
            helpful_scores_item = ScoringResultAttributesHelpfulScoresItem.from_dict(
                helpful_scores_item_data
            )

            helpful_scores.append(helpful_scores_item)

        auxiliary_info = []
        _auxiliary_info = d.pop("auxiliary_info")
        for auxiliary_info_item_data in _auxiliary_info:
            auxiliary_info_item = ScoringResultAttributesAuxiliaryInfoItem.from_dict(
                auxiliary_info_item_data
            )

            auxiliary_info.append(auxiliary_info_item)

        scoring_result_attributes = cls(
            scored_notes=scored_notes,
            helpful_scores=helpful_scores,
            auxiliary_info=auxiliary_info,
        )

        scoring_result_attributes.additional_properties = d
        return scoring_result_attributes

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
