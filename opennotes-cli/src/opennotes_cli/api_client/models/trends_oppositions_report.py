from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.claim_opposition import ClaimOpposition
    from ..models.claim_trend import ClaimTrend


T = TypeVar("T", bound="TrendsOppositionsReport")


@_attrs_define
class TrendsOppositionsReport:
    """
    Attributes:
        trends (list[ClaimTrend]):
        oppositions (list[ClaimOpposition]):
        input_cluster_count (int):
        skipped_for_cap (int):
    """

    trends: list[ClaimTrend]
    oppositions: list[ClaimOpposition]
    input_cluster_count: int
    skipped_for_cap: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        trends = []
        for trends_item_data in self.trends:
            trends_item = trends_item_data.to_dict()
            trends.append(trends_item)

        oppositions = []
        for oppositions_item_data in self.oppositions:
            oppositions_item = oppositions_item_data.to_dict()
            oppositions.append(oppositions_item)

        input_cluster_count = self.input_cluster_count

        skipped_for_cap = self.skipped_for_cap

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "trends": trends,
                "oppositions": oppositions,
                "input_cluster_count": input_cluster_count,
                "skipped_for_cap": skipped_for_cap,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.claim_opposition import ClaimOpposition
        from ..models.claim_trend import ClaimTrend

        d = dict(src_dict)
        trends = []
        _trends = d.pop("trends")
        for trends_item_data in _trends:
            trends_item = ClaimTrend.from_dict(trends_item_data)

            trends.append(trends_item)

        oppositions = []
        _oppositions = d.pop("oppositions")
        for oppositions_item_data in _oppositions:
            oppositions_item = ClaimOpposition.from_dict(oppositions_item_data)

            oppositions.append(oppositions_item)

        input_cluster_count = d.pop("input_cluster_count")

        skipped_for_cap = d.pop("skipped_for_cap")

        trends_oppositions_report = cls(
            trends=trends,
            oppositions=oppositions,
            input_cluster_count=input_cluster_count,
            skipped_for_cap=skipped_for_cap,
        )

        trends_oppositions_report.additional_properties = d
        return trends_oppositions_report

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
