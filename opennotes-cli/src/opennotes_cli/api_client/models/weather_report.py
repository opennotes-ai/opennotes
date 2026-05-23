from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.weather_axis_literalinsightful_on_topic_chatty_drifting_off_topic import (
        WeatherAxisLiteralinsightfulOnTopicChattyDriftingOffTopic,
    )
    from ..models.weather_axis_literalsourced_factual_claims_first_person_hearsay_misleading import (
        WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleading,
    )
    from ..models.weather_axisstr import WeatherAxisstr


T = TypeVar("T", bound="WeatherReport")


@_attrs_define
class WeatherReport:
    """
    Attributes:
        truth (WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleading):
        relevance (WeatherAxisLiteralinsightfulOnTopicChattyDriftingOffTopic):
        sentiment (WeatherAxisstr):
    """

    truth: WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleading
    relevance: WeatherAxisLiteralinsightfulOnTopicChattyDriftingOffTopic
    sentiment: WeatherAxisstr
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        truth = self.truth.to_dict()

        relevance = self.relevance.to_dict()

        sentiment = self.sentiment.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "truth": truth,
                "relevance": relevance,
                "sentiment": sentiment,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.weather_axis_literalinsightful_on_topic_chatty_drifting_off_topic import (
            WeatherAxisLiteralinsightfulOnTopicChattyDriftingOffTopic,
        )
        from ..models.weather_axis_literalsourced_factual_claims_first_person_hearsay_misleading import (
            WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleading,
        )
        from ..models.weather_axisstr import WeatherAxisstr

        d = dict(src_dict)
        truth = WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleading.from_dict(
            d.pop("truth")
        )

        relevance = WeatherAxisLiteralinsightfulOnTopicChattyDriftingOffTopic.from_dict(
            d.pop("relevance")
        )

        sentiment = WeatherAxisstr.from_dict(d.pop("sentiment"))

        weather_report = cls(
            truth=truth,
            relevance=relevance,
            sentiment=sentiment,
        )

        weather_report.additional_properties = d
        return weather_report

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
