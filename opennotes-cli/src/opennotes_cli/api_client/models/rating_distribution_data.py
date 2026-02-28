from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.per_agent_rating_data import PerAgentRatingData
    from ..models.rating_distribution_data_overall import RatingDistributionDataOverall


T = TypeVar("T", bound="RatingDistributionData")


@_attrs_define
class RatingDistributionData:
    """
    Attributes:
        overall (RatingDistributionDataOverall):
        per_agent (list[PerAgentRatingData]):
        total_ratings (int):
    """

    overall: RatingDistributionDataOverall
    per_agent: list[PerAgentRatingData]
    total_ratings: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        overall = self.overall.to_dict()

        per_agent = []
        for per_agent_item_data in self.per_agent:
            per_agent_item = per_agent_item_data.to_dict()
            per_agent.append(per_agent_item)

        total_ratings = self.total_ratings

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "overall": overall,
                "per_agent": per_agent,
                "total_ratings": total_ratings,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.per_agent_rating_data import PerAgentRatingData
        from ..models.rating_distribution_data_overall import (
            RatingDistributionDataOverall,
        )

        d = dict(src_dict)
        overall = RatingDistributionDataOverall.from_dict(d.pop("overall"))

        per_agent = []
        _per_agent = d.pop("per_agent")
        for per_agent_item_data in _per_agent:
            per_agent_item = PerAgentRatingData.from_dict(per_agent_item_data)

            per_agent.append(per_agent_item)

        total_ratings = d.pop("total_ratings")

        rating_distribution_data = cls(
            overall=overall,
            per_agent=per_agent,
            total_ratings=total_ratings,
        )

        rating_distribution_data.additional_properties = d
        return rating_distribution_data

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
