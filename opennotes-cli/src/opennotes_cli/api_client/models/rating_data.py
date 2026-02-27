from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="RatingData")


@_attrs_define
class RatingData:
    """
    Attributes:
        rater_participant_id (str):
        note_id (int):
        created_at_millis (int):
        helpfulness_level (str):
    """

    rater_participant_id: str
    note_id: int
    created_at_millis: int
    helpfulness_level: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rater_participant_id = self.rater_participant_id

        note_id = self.note_id

        created_at_millis = self.created_at_millis

        helpfulness_level = self.helpfulness_level

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "raterParticipantId": rater_participant_id,
                "noteId": note_id,
                "createdAtMillis": created_at_millis,
                "helpfulnessLevel": helpfulness_level,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rater_participant_id = d.pop("raterParticipantId")

        note_id = d.pop("noteId")

        created_at_millis = d.pop("createdAtMillis")

        helpfulness_level = d.pop("helpfulnessLevel")

        rating_data = cls(
            rater_participant_id=rater_participant_id,
            note_id=note_id,
            created_at_millis=created_at_millis,
            helpfulness_level=helpfulness_level,
        )

        rating_data.additional_properties = d
        return rating_data

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
