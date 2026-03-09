from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.scoring_history_snapshot_attributes_snapshot import (
        ScoringHistorySnapshotAttributesSnapshot,
    )


T = TypeVar("T", bound="ScoringHistorySnapshotAttributes")


@_attrs_define
class ScoringHistorySnapshotAttributes:
    """
    Attributes:
        timestamp (str): ISO 8601 timestamp of the snapshot
        snapshot (ScoringHistorySnapshotAttributesSnapshot): Full scoring snapshot data
    """

    timestamp: str
    snapshot: ScoringHistorySnapshotAttributesSnapshot
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        timestamp = self.timestamp

        snapshot = self.snapshot.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "timestamp": timestamp,
                "snapshot": snapshot,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.scoring_history_snapshot_attributes_snapshot import (
            ScoringHistorySnapshotAttributesSnapshot,
        )

        d = dict(src_dict)
        timestamp = d.pop("timestamp")

        snapshot = ScoringHistorySnapshotAttributesSnapshot.from_dict(d.pop("snapshot"))

        scoring_history_snapshot_attributes = cls(
            timestamp=timestamp,
            snapshot=snapshot,
        )

        scoring_history_snapshot_attributes.additional_properties = d
        return scoring_history_snapshot_attributes

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
