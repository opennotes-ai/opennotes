from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.timeline_bucket_data_notes_by_status import (
        TimelineBucketDataNotesByStatus,
    )
    from ..models.timeline_bucket_data_ratings_by_level import (
        TimelineBucketDataRatingsByLevel,
    )


T = TypeVar("T", bound="TimelineBucketData")


@_attrs_define
class TimelineBucketData:
    """
    Attributes:
        timestamp (str):
        notes_by_status (TimelineBucketDataNotesByStatus | Unset):
        ratings_by_level (TimelineBucketDataRatingsByLevel | Unset):
    """

    timestamp: str
    notes_by_status: TimelineBucketDataNotesByStatus | Unset = UNSET
    ratings_by_level: TimelineBucketDataRatingsByLevel | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        timestamp = self.timestamp

        notes_by_status: dict[str, Any] | Unset = UNSET
        if not isinstance(self.notes_by_status, Unset):
            notes_by_status = self.notes_by_status.to_dict()

        ratings_by_level: dict[str, Any] | Unset = UNSET
        if not isinstance(self.ratings_by_level, Unset):
            ratings_by_level = self.ratings_by_level.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "timestamp": timestamp,
            }
        )
        if notes_by_status is not UNSET:
            field_dict["notes_by_status"] = notes_by_status
        if ratings_by_level is not UNSET:
            field_dict["ratings_by_level"] = ratings_by_level

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.timeline_bucket_data_notes_by_status import (
            TimelineBucketDataNotesByStatus,
        )
        from ..models.timeline_bucket_data_ratings_by_level import (
            TimelineBucketDataRatingsByLevel,
        )

        d = dict(src_dict)
        timestamp = d.pop("timestamp")

        _notes_by_status = d.pop("notes_by_status", UNSET)
        notes_by_status: TimelineBucketDataNotesByStatus | Unset
        if isinstance(_notes_by_status, Unset):
            notes_by_status = UNSET
        else:
            notes_by_status = TimelineBucketDataNotesByStatus.from_dict(
                _notes_by_status
            )

        _ratings_by_level = d.pop("ratings_by_level", UNSET)
        ratings_by_level: TimelineBucketDataRatingsByLevel | Unset
        if isinstance(_ratings_by_level, Unset):
            ratings_by_level = UNSET
        else:
            ratings_by_level = TimelineBucketDataRatingsByLevel.from_dict(
                _ratings_by_level
            )

        timeline_bucket_data = cls(
            timestamp=timestamp,
            notes_by_status=notes_by_status,
            ratings_by_level=ratings_by_level,
        )

        timeline_bucket_data.additional_properties = d
        return timeline_bucket_data

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
