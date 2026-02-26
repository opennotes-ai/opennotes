from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="RecentScanAttributes")


@_attrs_define
class RecentScanAttributes:
    """Attributes for recent scan check.

    Attributes:
        has_recent_scan (bool): Whether community has a recent scan
    """

    has_recent_scan: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        has_recent_scan = self.has_recent_scan

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "has_recent_scan": has_recent_scan,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        has_recent_scan = d.pop("has_recent_scan")

        recent_scan_attributes = cls(
            has_recent_scan=has_recent_scan,
        )

        recent_scan_attributes.additional_properties = d
        return recent_scan_attributes

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
