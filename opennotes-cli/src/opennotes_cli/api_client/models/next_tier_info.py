from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="NextTierInfo")


@_attrs_define
class NextTierInfo:
    """
    Attributes:
        tier (str): Name of the next tier
        notes_needed (int): Total notes needed to reach next tier
        notes_to_upgrade (int): Additional notes needed (negative means already exceeded)
    """

    tier: str
    notes_needed: int
    notes_to_upgrade: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tier = self.tier

        notes_needed = self.notes_needed

        notes_to_upgrade = self.notes_to_upgrade

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tier": tier,
                "notes_needed": notes_needed,
                "notes_to_upgrade": notes_to_upgrade,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tier = d.pop("tier")

        notes_needed = d.pop("notes_needed")

        notes_to_upgrade = d.pop("notes_to_upgrade")

        next_tier_info = cls(
            tier=tier,
            notes_needed=notes_needed,
            notes_to_upgrade=notes_to_upgrade,
        )

        next_tier_info.additional_properties = d
        return next_tier_info

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
