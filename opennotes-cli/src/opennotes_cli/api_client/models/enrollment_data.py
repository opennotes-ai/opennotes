from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="EnrollmentData")


@_attrs_define
class EnrollmentData:
    """
    Attributes:
        participant_id (str):
        enrollment_state (str):
        successful_rating_needed_to_earn_in (int):
        timestamp_of_last_state_change (int):
    """

    participant_id: str
    enrollment_state: str
    successful_rating_needed_to_earn_in: int
    timestamp_of_last_state_change: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        participant_id = self.participant_id

        enrollment_state = self.enrollment_state

        successful_rating_needed_to_earn_in = self.successful_rating_needed_to_earn_in

        timestamp_of_last_state_change = self.timestamp_of_last_state_change

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "participantId": participant_id,
                "enrollmentState": enrollment_state,
                "successfulRatingNeededToEarnIn": successful_rating_needed_to_earn_in,
                "timestampOfLastStateChange": timestamp_of_last_state_change,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        participant_id = d.pop("participantId")

        enrollment_state = d.pop("enrollmentState")

        successful_rating_needed_to_earn_in = d.pop("successfulRatingNeededToEarnIn")

        timestamp_of_last_state_change = d.pop("timestampOfLastStateChange")

        enrollment_data = cls(
            participant_id=participant_id,
            enrollment_state=enrollment_state,
            successful_rating_needed_to_earn_in=successful_rating_needed_to_earn_in,
            timestamp_of_last_state_change=timestamp_of_last_state_change,
        )

        enrollment_data.additional_properties = d
        return enrollment_data

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
