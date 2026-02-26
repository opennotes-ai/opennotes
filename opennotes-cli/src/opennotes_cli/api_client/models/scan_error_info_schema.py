from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ScanErrorInfoSchema")


@_attrs_define
class ScanErrorInfoSchema:
    """Error information for a failed message scan.

    Attributes:
        error_type (str): Type of error (e.g., 'TypeError')
        error_message (str): Error message details
        message_id (None | str | Unset): Message ID that caused error
        batch_number (int | None | Unset): Batch number where error occurred
    """

    error_type: str
    error_message: str
    message_id: None | str | Unset = UNSET
    batch_number: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        error_type = self.error_type

        error_message = self.error_message

        message_id: None | str | Unset
        if isinstance(self.message_id, Unset):
            message_id = UNSET
        else:
            message_id = self.message_id

        batch_number: int | None | Unset
        if isinstance(self.batch_number, Unset):
            batch_number = UNSET
        else:
            batch_number = self.batch_number

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "error_type": error_type,
                "error_message": error_message,
            }
        )
        if message_id is not UNSET:
            field_dict["message_id"] = message_id
        if batch_number is not UNSET:
            field_dict["batch_number"] = batch_number

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        error_type = d.pop("error_type")

        error_message = d.pop("error_message")

        def _parse_message_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message_id = _parse_message_id(d.pop("message_id", UNSET))

        def _parse_batch_number(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        batch_number = _parse_batch_number(d.pop("batch_number", UNSET))

        scan_error_info_schema = cls(
            error_type=error_type,
            error_message=error_message,
            message_id=message_id,
            batch_number=batch_number,
        )

        scan_error_info_schema.additional_properties = d
        return scan_error_info_schema

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
