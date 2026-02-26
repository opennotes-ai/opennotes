from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="RatingStatsAttributes")


@_attrs_define
class RatingStatsAttributes:
    """Attributes for rating statistics.

    Attributes:
        total (int): Total number of ratings
        helpful (int): Number of HELPFUL ratings
        somewhat_helpful (int): Number of SOMEWHAT_HELPFUL ratings
        not_helpful (int): Number of NOT_HELPFUL ratings
        average_score (float): Average score (1-3 scale)
    """

    total: int
    helpful: int
    somewhat_helpful: int
    not_helpful: int
    average_score: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total = self.total

        helpful = self.helpful

        somewhat_helpful = self.somewhat_helpful

        not_helpful = self.not_helpful

        average_score = self.average_score

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total": total,
                "helpful": helpful,
                "somewhat_helpful": somewhat_helpful,
                "not_helpful": not_helpful,
                "average_score": average_score,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        total = d.pop("total")

        helpful = d.pop("helpful")

        somewhat_helpful = d.pop("somewhat_helpful")

        not_helpful = d.pop("not_helpful")

        average_score = d.pop("average_score")

        rating_stats_attributes = cls(
            total=total,
            helpful=helpful,
            somewhat_helpful=somewhat_helpful,
            not_helpful=not_helpful,
            average_score=average_score,
        )

        rating_stats_attributes.additional_properties = d
        return rating_stats_attributes

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
