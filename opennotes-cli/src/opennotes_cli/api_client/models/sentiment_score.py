from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.sentiment_score_label import SentimentScoreLabel

T = TypeVar("T", bound="SentimentScore")


@_attrs_define
class SentimentScore:
    """
    Attributes:
        utterance_id (str):
        label (SentimentScoreLabel):
        valence (float):
    """

    utterance_id: str
    label: SentimentScoreLabel
    valence: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        utterance_id = self.utterance_id

        label = self.label.value

        valence = self.valence

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "utterance_id": utterance_id,
                "label": label,
                "valence": valence,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        utterance_id = d.pop("utterance_id")

        label = SentimentScoreLabel(d.pop("label"))

        valence = d.pop("valence")

        sentiment_score = cls(
            utterance_id=utterance_id,
            label=label,
            valence=valence,
        )

        sentiment_score.additional_properties = d
        return sentiment_score

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
