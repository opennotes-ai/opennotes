from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.scan_error_info_schema import ScanErrorInfoSchema
    from ..models.scan_error_summary_schema_error_types import (
        ScanErrorSummarySchemaErrorTypes,
    )


T = TypeVar("T", bound="ScanErrorSummarySchema")


@_attrs_define
class ScanErrorSummarySchema:
    """Summary of errors encountered during scan.

    Attributes:
        total_errors (int | Unset): Total number of errors Default: 0.
        error_types (ScanErrorSummarySchemaErrorTypes | Unset): Count of errors by type
        sample_errors (list[ScanErrorInfoSchema] | Unset): Sample of error messages (up to 5)
    """

    total_errors: int | Unset = 0
    error_types: ScanErrorSummarySchemaErrorTypes | Unset = UNSET
    sample_errors: list[ScanErrorInfoSchema] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_errors = self.total_errors

        error_types: dict[str, Any] | Unset = UNSET
        if not isinstance(self.error_types, Unset):
            error_types = self.error_types.to_dict()

        sample_errors: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.sample_errors, Unset):
            sample_errors = []
            for sample_errors_item_data in self.sample_errors:
                sample_errors_item = sample_errors_item_data.to_dict()
                sample_errors.append(sample_errors_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if total_errors is not UNSET:
            field_dict["total_errors"] = total_errors
        if error_types is not UNSET:
            field_dict["error_types"] = error_types
        if sample_errors is not UNSET:
            field_dict["sample_errors"] = sample_errors

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.scan_error_info_schema import ScanErrorInfoSchema
        from ..models.scan_error_summary_schema_error_types import (
            ScanErrorSummarySchemaErrorTypes,
        )

        d = dict(src_dict)
        total_errors = d.pop("total_errors", UNSET)

        _error_types = d.pop("error_types", UNSET)
        error_types: ScanErrorSummarySchemaErrorTypes | Unset
        if isinstance(_error_types, Unset):
            error_types = UNSET
        else:
            error_types = ScanErrorSummarySchemaErrorTypes.from_dict(_error_types)

        _sample_errors = d.pop("sample_errors", UNSET)
        sample_errors: list[ScanErrorInfoSchema] | Unset = UNSET
        if _sample_errors is not UNSET:
            sample_errors = []
            for sample_errors_item_data in _sample_errors:
                sample_errors_item = ScanErrorInfoSchema.from_dict(
                    sample_errors_item_data
                )

                sample_errors.append(sample_errors_item)

        scan_error_summary_schema = cls(
            total_errors=total_errors,
            error_types=error_types,
            sample_errors=sample_errors,
        )

        scan_error_summary_schema.additional_properties = d
        return scan_error_summary_schema

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
