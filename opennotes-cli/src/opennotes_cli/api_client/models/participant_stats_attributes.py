from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ParticipantStatsAttributes")


@_attrs_define
class ParticipantStatsAttributes:
    """Attributes for participant statistics resource.

    Attributes:
        notes_created (int):
        ratings_given (int):
        average_helpfulness_received (float):
        top_classification (None | str | Unset):
    """

    notes_created: int
    ratings_given: int
    average_helpfulness_received: float
    top_classification: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        notes_created = self.notes_created

        ratings_given = self.ratings_given

        average_helpfulness_received = self.average_helpfulness_received

        top_classification: None | str | Unset
        if isinstance(self.top_classification, Unset):
            top_classification = UNSET
        else:
            top_classification = self.top_classification

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "notes_created": notes_created,
                "ratings_given": ratings_given,
                "average_helpfulness_received": average_helpfulness_received,
            }
        )
        if top_classification is not UNSET:
            field_dict["top_classification"] = top_classification

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        notes_created = d.pop("notes_created")

        ratings_given = d.pop("ratings_given")

        average_helpfulness_received = d.pop("average_helpfulness_received")

        def _parse_top_classification(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        top_classification = _parse_top_classification(
            d.pop("top_classification", UNSET)
        )

        participant_stats_attributes = cls(
            notes_created=notes_created,
            ratings_given=ratings_given,
            average_helpfulness_received=average_helpfulness_received,
            top_classification=top_classification,
        )

        participant_stats_attributes.additional_properties = d
        return participant_stats_attributes

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
