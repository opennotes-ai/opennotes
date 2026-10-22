from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.highlights_threshold_info import HighlightsThresholdInfo
    from ..models.opinions_highlight import OpinionsHighlight


T = TypeVar("T", bound="OpinionsHighlightsReport")


@_attrs_define
class OpinionsHighlightsReport:
    """
    Attributes:
        highlights (list[OpinionsHighlight]):
        threshold (HighlightsThresholdInfo):
        fallback_engaged (bool):
        floor_eligible_count (int):
        total_input_count (int):
    """

    highlights: list[OpinionsHighlight]
    threshold: HighlightsThresholdInfo
    fallback_engaged: bool
    floor_eligible_count: int
    total_input_count: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        highlights = []
        for highlights_item_data in self.highlights:
            highlights_item = highlights_item_data.to_dict()
            highlights.append(highlights_item)

        threshold = self.threshold.to_dict()

        fallback_engaged = self.fallback_engaged

        floor_eligible_count = self.floor_eligible_count

        total_input_count = self.total_input_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "highlights": highlights,
                "threshold": threshold,
                "fallback_engaged": fallback_engaged,
                "floor_eligible_count": floor_eligible_count,
                "total_input_count": total_input_count,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.highlights_threshold_info import HighlightsThresholdInfo
        from ..models.opinions_highlight import OpinionsHighlight

        d = dict(src_dict)
        highlights = []
        _highlights = d.pop("highlights")
        for highlights_item_data in _highlights:
            highlights_item = OpinionsHighlight.from_dict(highlights_item_data)

            highlights.append(highlights_item)

        threshold = HighlightsThresholdInfo.from_dict(d.pop("threshold"))

        fallback_engaged = d.pop("fallback_engaged")

        floor_eligible_count = d.pop("floor_eligible_count")

        total_input_count = d.pop("total_input_count")

        opinions_highlights_report = cls(
            highlights=highlights,
            threshold=threshold,
            fallback_engaged=fallback_engaged,
            floor_eligible_count=floor_eligible_count,
            total_input_count=total_input_count,
        )

        opinions_highlights_report.additional_properties = d
        return opinions_highlights_report

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
