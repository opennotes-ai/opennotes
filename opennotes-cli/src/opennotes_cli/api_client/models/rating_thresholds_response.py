from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="RatingThresholdsResponse")


@_attrs_define
class RatingThresholdsResponse:
    """
    Attributes:
        min_ratings_needed (int): Minimum number of ratings before a note can receive CRH/CRNH status
        min_raters_per_note (int): Minimum number of unique raters required per note
    """

    min_ratings_needed: int
    min_raters_per_note: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        min_ratings_needed = self.min_ratings_needed

        min_raters_per_note = self.min_raters_per_note

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "min_ratings_needed": min_ratings_needed,
                "min_raters_per_note": min_raters_per_note,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        min_ratings_needed = d.pop("min_ratings_needed")

        min_raters_per_note = d.pop("min_raters_per_note")

        rating_thresholds_response = cls(
            min_ratings_needed=min_ratings_needed,
            min_raters_per_note=min_raters_per_note,
        )

        rating_thresholds_response.additional_properties = d
        return rating_thresholds_response

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
