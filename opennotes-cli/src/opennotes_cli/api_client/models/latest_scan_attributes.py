from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.scan_error_summary_schema import ScanErrorSummarySchema


T = TypeVar("T", bound="LatestScanAttributes")


@_attrs_define
class LatestScanAttributes:
    """Attributes for the latest scan resource.

    Attributes:
        status (str): Scan status: pending, in_progress, completed, failed
        initiated_at (datetime.datetime): When the scan was initiated
        completed_at (datetime.datetime | None | Unset): When the scan completed
        messages_scanned (int | Unset): Total messages scanned Default: 0.
        messages_flagged (int | Unset): Number of flagged messages Default: 0.
        error_summary (None | ScanErrorSummarySchema | Unset): Summary of errors encountered during scan
    """

    status: str
    initiated_at: datetime.datetime
    completed_at: datetime.datetime | None | Unset = UNSET
    messages_scanned: int | Unset = 0
    messages_flagged: int | Unset = 0
    error_summary: None | ScanErrorSummarySchema | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.scan_error_summary_schema import ScanErrorSummarySchema

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

        error_summary: dict[str, Any] | None | Unset
        if isinstance(self.error_summary, Unset):
            error_summary = UNSET
        elif isinstance(self.error_summary, ScanErrorSummarySchema):
            error_summary = self.error_summary.to_dict()
        else:
            error_summary = self.error_summary

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
        if error_summary is not UNSET:
            field_dict["error_summary"] = error_summary

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.scan_error_summary_schema import ScanErrorSummarySchema

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

        def _parse_error_summary(data: object) -> None | ScanErrorSummarySchema | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                error_summary_type_0 = ScanErrorSummarySchema.from_dict(data)

                return error_summary_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ScanErrorSummarySchema | Unset, data)

        error_summary = _parse_error_summary(d.pop("error_summary", UNSET))

        latest_scan_attributes = cls(
            status=status,
            initiated_at=initiated_at,
            completed_at=completed_at,
            messages_scanned=messages_scanned,
            messages_flagged=messages_flagged,
            error_summary=error_summary,
        )

        latest_scan_attributes.additional_properties = d
        return latest_scan_attributes

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
