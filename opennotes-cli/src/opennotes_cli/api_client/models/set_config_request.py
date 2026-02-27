from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="SetConfigRequest")


@_attrs_define
class SetConfigRequest:
    """
    Attributes:
        key (str): Configuration key to set (snake_case: lowercase letters, numbers, underscores, must start with
            letter)
        value (str): Configuration value (stringified)
    """

    key: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        key = self.key

        value = self.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "key": key,
                "value": value,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        value = d.pop("value")

        set_config_request = cls(
            key=key,
            value=value,
        )

        return set_config_request
