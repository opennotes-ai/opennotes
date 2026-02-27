from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TierInfo")


@_attrs_define
class TierInfo:
    """
    Attributes:
        level (int): Numeric tier level (0-5)
        name (str): Human-readable tier name
        scorer_components (list[str]): List of scorer components active in this tier
    """

    level: int
    name: str
    scorer_components: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        level = self.level

        name = self.name

        scorer_components = self.scorer_components

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "level": level,
                "name": name,
                "scorer_components": scorer_components,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        level = d.pop("level")

        name = d.pop("name")

        scorer_components = cast(list[str], d.pop("scorer_components"))

        tier_info = cls(
            level=level,
            name=name,
            scorer_components=scorer_components,
        )

        tier_info.additional_properties = d
        return tier_info

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
