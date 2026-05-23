from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.harmful_content_match import HarmfulContentMatch
    from ..models.safety_recommendation import SafetyRecommendation


T = TypeVar("T", bound="SafetySection")


@_attrs_define
class SafetySection:
    """
    Attributes:
        harmful_content_matches (list[HarmfulContentMatch] | Unset):
        recommendation (None | SafetyRecommendation | Unset):
    """

    harmful_content_matches: list[HarmfulContentMatch] | Unset = UNSET
    recommendation: None | SafetyRecommendation | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.safety_recommendation import SafetyRecommendation

        harmful_content_matches: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.harmful_content_matches, Unset):
            harmful_content_matches = []
            for harmful_content_matches_item_data in self.harmful_content_matches:
                harmful_content_matches_item = (
                    harmful_content_matches_item_data.to_dict()
                )
                harmful_content_matches.append(harmful_content_matches_item)

        recommendation: dict[str, Any] | None | Unset
        if isinstance(self.recommendation, Unset):
            recommendation = UNSET
        elif isinstance(self.recommendation, SafetyRecommendation):
            recommendation = self.recommendation.to_dict()
        else:
            recommendation = self.recommendation

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if harmful_content_matches is not UNSET:
            field_dict["harmful_content_matches"] = harmful_content_matches
        if recommendation is not UNSET:
            field_dict["recommendation"] = recommendation

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.harmful_content_match import HarmfulContentMatch
        from ..models.safety_recommendation import SafetyRecommendation

        d = dict(src_dict)
        _harmful_content_matches = d.pop("harmful_content_matches", UNSET)
        harmful_content_matches: list[HarmfulContentMatch] | Unset = UNSET
        if _harmful_content_matches is not UNSET:
            harmful_content_matches = []
            for harmful_content_matches_item_data in _harmful_content_matches:
                harmful_content_matches_item = HarmfulContentMatch.from_dict(
                    harmful_content_matches_item_data
                )

                harmful_content_matches.append(harmful_content_matches_item)

        def _parse_recommendation(data: object) -> None | SafetyRecommendation | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                recommendation_type_0 = SafetyRecommendation.from_dict(data)

                return recommendation_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SafetyRecommendation | Unset, data)

        recommendation = _parse_recommendation(d.pop("recommendation", UNSET))

        safety_section = cls(
            harmful_content_matches=harmful_content_matches,
            recommendation=recommendation,
        )

        safety_section.additional_properties = d
        return safety_section

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
