from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="BulkScanCreateAttributes")


@_attrs_define
class BulkScanCreateAttributes:
    """Attributes for creating a bulk scan.

    Attributes:
        community_server_id (UUID): Community server UUID to scan
        scan_window_days (int | Unset): Number of days to scan back Default: 7.
        channel_ids (list[str] | Unset): Specific channel IDs to scan (empty = all channels)
    """

    community_server_id: UUID
    scan_window_days: int | Unset = 7
    channel_ids: list[str] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        community_server_id = str(self.community_server_id)

        scan_window_days = self.scan_window_days

        channel_ids: list[str] | Unset = UNSET
        if not isinstance(self.channel_ids, Unset):
            channel_ids = self.channel_ids

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "community_server_id": community_server_id,
            }
        )
        if scan_window_days is not UNSET:
            field_dict["scan_window_days"] = scan_window_days
        if channel_ids is not UNSET:
            field_dict["channel_ids"] = channel_ids

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        community_server_id = UUID(d.pop("community_server_id"))

        scan_window_days = d.pop("scan_window_days", UNSET)

        channel_ids = cast(list[str], d.pop("channel_ids", UNSET))

        bulk_scan_create_attributes = cls(
            community_server_id=community_server_id,
            scan_window_days=scan_window_days,
            channel_ids=channel_ids,
        )

        return bulk_scan_create_attributes
