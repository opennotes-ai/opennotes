from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.opinions_highlights_report import OpinionsHighlightsReport
    from ..models.opinions_report import OpinionsReport
    from ..models.trends_oppositions_report import TrendsOppositionsReport


T = TypeVar("T", bound="OpinionsSection")


@_attrs_define
class OpinionsSection:
    """
    Attributes:
        opinions_report (OpinionsReport):
        trends_oppositions (None | TrendsOppositionsReport | Unset):
        highlights (None | OpinionsHighlightsReport | Unset):
    """

    opinions_report: OpinionsReport
    trends_oppositions: None | TrendsOppositionsReport | Unset = UNSET
    highlights: None | OpinionsHighlightsReport | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.opinions_highlights_report import OpinionsHighlightsReport
        from ..models.trends_oppositions_report import TrendsOppositionsReport

        opinions_report = self.opinions_report.to_dict()

        trends_oppositions: dict[str, Any] | None | Unset
        if isinstance(self.trends_oppositions, Unset):
            trends_oppositions = UNSET
        elif isinstance(self.trends_oppositions, TrendsOppositionsReport):
            trends_oppositions = self.trends_oppositions.to_dict()
        else:
            trends_oppositions = self.trends_oppositions

        highlights: dict[str, Any] | None | Unset
        if isinstance(self.highlights, Unset):
            highlights = UNSET
        elif isinstance(self.highlights, OpinionsHighlightsReport):
            highlights = self.highlights.to_dict()
        else:
            highlights = self.highlights

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "opinions_report": opinions_report,
            }
        )
        if trends_oppositions is not UNSET:
            field_dict["trends_oppositions"] = trends_oppositions
        if highlights is not UNSET:
            field_dict["highlights"] = highlights

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.opinions_highlights_report import OpinionsHighlightsReport
        from ..models.opinions_report import OpinionsReport
        from ..models.trends_oppositions_report import TrendsOppositionsReport

        d = dict(src_dict)
        opinions_report = OpinionsReport.from_dict(d.pop("opinions_report"))

        def _parse_trends_oppositions(
            data: object,
        ) -> None | TrendsOppositionsReport | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                trends_oppositions_type_0 = TrendsOppositionsReport.from_dict(data)

                return trends_oppositions_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TrendsOppositionsReport | Unset, data)

        trends_oppositions = _parse_trends_oppositions(
            d.pop("trends_oppositions", UNSET)
        )

        def _parse_highlights(data: object) -> None | OpinionsHighlightsReport | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                highlights_type_0 = OpinionsHighlightsReport.from_dict(data)

                return highlights_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OpinionsHighlightsReport | Unset, data)

        highlights = _parse_highlights(d.pop("highlights", UNSET))

        opinions_section = cls(
            opinions_report=opinions_report,
            trends_oppositions=trends_oppositions,
            highlights=highlights,
        )

        opinions_section.additional_properties = d
        return opinions_section

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
