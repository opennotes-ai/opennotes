from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.weather_axis_alternative_literalinsightful_on_topic_chatty_drifting_off_topic_label import (
    WeatherAxisAlternativeLiteralinsightfulOnTopicChattyDriftingOffTopicLabel,
)
from ..types import UNSET, Unset

T = TypeVar(
    "T", bound="WeatherAxisAlternativeLiteralinsightfulOnTopicChattyDriftingOffTopic"
)


@_attrs_define
class WeatherAxisAlternativeLiteralinsightfulOnTopicChattyDriftingOffTopic:
    """
    Attributes:
        label (WeatherAxisAlternativeLiteralinsightfulOnTopicChattyDriftingOffTopicLabel):
        logprob (float | None | Unset):
    """

    label: WeatherAxisAlternativeLiteralinsightfulOnTopicChattyDriftingOffTopicLabel
    logprob: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        label = self.label.value

        logprob: float | None | Unset
        if isinstance(self.logprob, Unset):
            logprob = UNSET
        else:
            logprob = self.logprob

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "label": label,
            }
        )
        if logprob is not UNSET:
            field_dict["logprob"] = logprob

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        label = (
            WeatherAxisAlternativeLiteralinsightfulOnTopicChattyDriftingOffTopicLabel(
                d.pop("label")
            )
        )

        def _parse_logprob(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        logprob = _parse_logprob(d.pop("logprob", UNSET))

        weather_axis_alternative_literalinsightful_on_topic_chatty_drifting_off_topic = cls(
            label=label,
            logprob=logprob,
        )

        weather_axis_alternative_literalinsightful_on_topic_chatty_drifting_off_topic.additional_properties = d
        return weather_axis_alternative_literalinsightful_on_topic_chatty_drifting_off_topic

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
