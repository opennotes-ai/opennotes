from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.harmful_content_match_source import HarmfulContentMatchSource
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.harmful_content_match_categories import HarmfulContentMatchCategories
    from ..models.harmful_content_match_scores import HarmfulContentMatchScores


T = TypeVar("T", bound="HarmfulContentMatch")


@_attrs_define
class HarmfulContentMatch:
    """
    Attributes:
        utterance_id (str):
        max_score (float):
        categories (HarmfulContentMatchCategories):
        scores (HarmfulContentMatchScores):
        utterance_text (str | Unset):  Default: ''.
        flagged_categories (list[str] | Unset):
        source (HarmfulContentMatchSource | Unset):  Default: HarmfulContentMatchSource.OPENAI.
    """

    utterance_id: str
    max_score: float
    categories: HarmfulContentMatchCategories
    scores: HarmfulContentMatchScores
    utterance_text: str | Unset = ""
    flagged_categories: list[str] | Unset = UNSET
    source: HarmfulContentMatchSource | Unset = HarmfulContentMatchSource.OPENAI
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        utterance_id = self.utterance_id

        max_score = self.max_score

        categories = self.categories.to_dict()

        scores = self.scores.to_dict()

        utterance_text = self.utterance_text

        flagged_categories: list[str] | Unset = UNSET
        if not isinstance(self.flagged_categories, Unset):
            flagged_categories = self.flagged_categories

        source: str | Unset = UNSET
        if not isinstance(self.source, Unset):
            source = self.source.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "utterance_id": utterance_id,
                "max_score": max_score,
                "categories": categories,
                "scores": scores,
            }
        )
        if utterance_text is not UNSET:
            field_dict["utterance_text"] = utterance_text
        if flagged_categories is not UNSET:
            field_dict["flagged_categories"] = flagged_categories
        if source is not UNSET:
            field_dict["source"] = source

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.harmful_content_match_categories import (
            HarmfulContentMatchCategories,
        )
        from ..models.harmful_content_match_scores import HarmfulContentMatchScores

        d = dict(src_dict)
        utterance_id = d.pop("utterance_id")

        max_score = d.pop("max_score")

        categories = HarmfulContentMatchCategories.from_dict(d.pop("categories"))

        scores = HarmfulContentMatchScores.from_dict(d.pop("scores"))

        utterance_text = d.pop("utterance_text", UNSET)

        flagged_categories = cast(list[str], d.pop("flagged_categories", UNSET))

        _source = d.pop("source", UNSET)
        source: HarmfulContentMatchSource | Unset
        if isinstance(_source, Unset):
            source = UNSET
        else:
            source = HarmfulContentMatchSource(_source)

        harmful_content_match = cls(
            utterance_id=utterance_id,
            max_score=max_score,
            categories=categories,
            scores=scores,
            utterance_text=utterance_text,
            flagged_categories=flagged_categories,
            source=source,
        )

        harmful_content_match.additional_properties = d
        return harmful_content_match

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
