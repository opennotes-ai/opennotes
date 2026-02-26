from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.scan_error_summary_schema import ScanErrorSummarySchema


T = TypeVar("T", bound="BulkScanResultsAttributes")


@_attrs_define
class BulkScanResultsAttributes:
    """Attributes for bulk scan results.

    Attributes:
        status (str): Scan status
        messages_scanned (int | Unset): Total messages scanned Default: 0.
        messages_flagged (int | Unset): Number of flagged messages Default: 0.
        error_summary (None | ScanErrorSummarySchema | Unset): Summary of errors encountered during scan
    """

    status: str
    messages_scanned: int | Unset = 0
    messages_flagged: int | Unset = 0
    error_summary: None | ScanErrorSummarySchema | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.scan_error_summary_schema import ScanErrorSummarySchema

        status = self.status

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
            }
        )
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

        bulk_scan_results_attributes = cls(
            status=status,
            messages_scanned=messages_scanned,
            messages_flagged=messages_flagged,
            error_summary=error_summary,
        )

        bulk_scan_results_attributes.additional_properties = d
        return bulk_scan_results_attributes

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
