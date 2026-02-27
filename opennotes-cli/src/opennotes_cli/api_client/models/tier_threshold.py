from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TierThreshold")


@_attrs_define
class TierThreshold:
    """
    Attributes:
        min_ (int): Minimum note count for this tier
        max_ (int | None): Maximum note count for this tier (null for unlimited)
        current (bool): Whether this is the currently active tier
    """

    min_: int
    max_: int | None
    current: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        min_ = self.min_

        max_: int | None
        max_ = self.max_

        current = self.current

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "min": min_,
                "max": max_,
                "current": current,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        min_ = d.pop("min")

        def _parse_max_(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        max_ = _parse_max_(d.pop("max"))

        current = d.pop("current")

        tier_threshold = cls(
            min_=min_,
            max_=max_,
            current=current,
        )

        tier_threshold.additional_properties = d
        return tier_threshold

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
