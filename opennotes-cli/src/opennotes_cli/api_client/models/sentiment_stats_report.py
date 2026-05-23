from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.sentiment_score import SentimentScore


T = TypeVar("T", bound="SentimentStatsReport")


@_attrs_define
class SentimentStatsReport:
    """
    Attributes:
        per_utterance (list[SentimentScore]):
        positive_pct (float):
        negative_pct (float):
        neutral_pct (float):
        mean_valence (float):
    """

    per_utterance: list[SentimentScore]
    positive_pct: float
    negative_pct: float
    neutral_pct: float
    mean_valence: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        per_utterance = []
        for per_utterance_item_data in self.per_utterance:
            per_utterance_item = per_utterance_item_data.to_dict()
            per_utterance.append(per_utterance_item)

        positive_pct = self.positive_pct

        negative_pct = self.negative_pct

        neutral_pct = self.neutral_pct

        mean_valence = self.mean_valence

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "per_utterance": per_utterance,
                "positive_pct": positive_pct,
                "negative_pct": negative_pct,
                "neutral_pct": neutral_pct,
                "mean_valence": mean_valence,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.sentiment_score import SentimentScore

        d = dict(src_dict)
        per_utterance = []
        _per_utterance = d.pop("per_utterance")
        for per_utterance_item_data in _per_utterance:
            per_utterance_item = SentimentScore.from_dict(per_utterance_item_data)

            per_utterance.append(per_utterance_item)

        positive_pct = d.pop("positive_pct")

        negative_pct = d.pop("negative_pct")

        neutral_pct = d.pop("neutral_pct")

        mean_valence = d.pop("mean_valence")

        sentiment_stats_report = cls(
            per_utterance=per_utterance,
            positive_pct=positive_pct,
            negative_pct=negative_pct,
            neutral_pct=neutral_pct,
            mean_valence=mean_valence,
        )

        sentiment_stats_report.additional_properties = d
        return sentiment_stats_report

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
