from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="BulkScanAttributes")


@_attrs_define
class BulkScanAttributes:
    """Attributes for a bulk scan resource.

    Attributes:
        status (str): Scan status: pending, in_progress, completed, failed
        initiated_at (datetime.datetime): When the scan was initiated
        completed_at (datetime.datetime | None | Unset): When the scan completed
        messages_scanned (int | Unset): Total messages scanned Default: 0.
        messages_flagged (int | Unset): Number of flagged messages Default: 0.
    """

    status: str
    initiated_at: datetime.datetime
    completed_at: datetime.datetime | None | Unset = UNSET
    messages_scanned: int | Unset = 0
    messages_flagged: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        status = self.status

        initiated_at = self.initiated_at.isoformat()

        completed_at: None | str | Unset
        if isinstance(self.completed_at, Unset):
            completed_at = UNSET
        elif isinstance(self.completed_at, datetime.datetime):
            completed_at = self.completed_at.isoformat()
        else:
            completed_at = self.completed_at

        messages_scanned = self.messages_scanned

        messages_flagged = self.messages_flagged

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "status": status,
                "initiated_at": initiated_at,
            }
        )
        if completed_at is not UNSET:
            field_dict["completed_at"] = completed_at
        if messages_scanned is not UNSET:
            field_dict["messages_scanned"] = messages_scanned
        if messages_flagged is not UNSET:
            field_dict["messages_flagged"] = messages_flagged

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        status = d.pop("status")

        initiated_at = isoparse(d.pop("initiated_at"))

        def _parse_completed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                completed_at_type_0 = isoparse(data)

                return completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))

        messages_scanned = d.pop("messages_scanned", UNSET)

        messages_flagged = d.pop("messages_flagged", UNSET)

        bulk_scan_attributes = cls(
            status=status,
            initiated_at=initiated_at,
            completed_at=completed_at,
            messages_scanned=messages_scanned,
            messages_flagged=messages_flagged,
        )

        bulk_scan_attributes.additional_properties = d
        return bulk_scan_attributes

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
