from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.sentiment_stats_report import SentimentStatsReport
    from ..models.subjective_claim import SubjectiveClaim


T = TypeVar("T", bound="OpinionsReport")


@_attrs_define
class OpinionsReport:
    """
    Attributes:
        sentiment_stats (SentimentStatsReport):
        subjective_claims (list[SubjectiveClaim]):
    """

    sentiment_stats: SentimentStatsReport
    subjective_claims: list[SubjectiveClaim]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        sentiment_stats = self.sentiment_stats.to_dict()

        subjective_claims = []
        for subjective_claims_item_data in self.subjective_claims:
            subjective_claims_item = subjective_claims_item_data.to_dict()
            subjective_claims.append(subjective_claims_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sentiment_stats": sentiment_stats,
                "subjective_claims": subjective_claims,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.sentiment_stats_report import SentimentStatsReport
        from ..models.subjective_claim import SubjectiveClaim

        d = dict(src_dict)
        sentiment_stats = SentimentStatsReport.from_dict(d.pop("sentiment_stats"))

        subjective_claims = []
        _subjective_claims = d.pop("subjective_claims")
        for subjective_claims_item_data in _subjective_claims:
            subjective_claims_item = SubjectiveClaim.from_dict(
                subjective_claims_item_data
            )

            subjective_claims.append(subjective_claims_item)

        opinions_report = cls(
            sentiment_stats=sentiment_stats,
            subjective_claims=subjective_claims,
        )

        opinions_report.additional_properties = d
        return opinions_report

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
