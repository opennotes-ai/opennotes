from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TokenPoolStatus")


@_attrs_define
class TokenPoolStatus:
    """
    Attributes:
        pool_name (str):
        capacity (int):
        available (int):
        active_hold_count (int):
        utilization_pct (float):
    """

    pool_name: str
    capacity: int
    available: int
    active_hold_count: int
    utilization_pct: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        pool_name = self.pool_name

        capacity = self.capacity

        available = self.available

        active_hold_count = self.active_hold_count

        utilization_pct = self.utilization_pct

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "pool_name": pool_name,
                "capacity": capacity,
                "available": available,
                "active_hold_count": active_hold_count,
                "utilization_pct": utilization_pct,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        pool_name = d.pop("pool_name")

        capacity = d.pop("capacity")

        available = d.pop("available")

        active_hold_count = d.pop("active_hold_count")

        utilization_pct = d.pop("utilization_pct")

        token_pool_status = cls(
            pool_name=pool_name,
            capacity=capacity,
            available=available,
            active_hold_count=active_hold_count,
            utilization_pct=utilization_pct,
        )

        token_pool_status.additional_properties = d
        return token_pool_status

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
