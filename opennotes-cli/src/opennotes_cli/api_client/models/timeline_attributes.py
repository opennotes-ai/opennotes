from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.timeline_bucket_data import TimelineBucketData


T = TypeVar("T", bound="TimelineAttributes")


@_attrs_define
class TimelineAttributes:
    """
    Attributes:
        bucket_size (str):
        buckets (list[TimelineBucketData]):
        total_notes (int):
        total_ratings (int):
    """

    bucket_size: str
    buckets: list[TimelineBucketData]
    total_notes: int
    total_ratings: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        bucket_size = self.bucket_size

        buckets = []
        for buckets_item_data in self.buckets:
            buckets_item = buckets_item_data.to_dict()
            buckets.append(buckets_item)

        total_notes = self.total_notes

        total_ratings = self.total_ratings

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "bucket_size": bucket_size,
                "buckets": buckets,
                "total_notes": total_notes,
                "total_ratings": total_ratings,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.timeline_bucket_data import TimelineBucketData

        d = dict(src_dict)
        bucket_size = d.pop("bucket_size")

        buckets = []
        _buckets = d.pop("buckets")
        for buckets_item_data in _buckets:
            buckets_item = TimelineBucketData.from_dict(buckets_item_data)

            buckets.append(buckets_item)

        total_notes = d.pop("total_notes")

        total_ratings = d.pop("total_ratings")

        timeline_attributes = cls(
            bucket_size=bucket_size,
            buckets=buckets,
            total_notes=total_notes,
            total_ratings=total_ratings,
        )

        timeline_attributes.additional_properties = d
        return timeline_attributes

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
