from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

T = TypeVar("T", bound="AdminAPIKeyCreate")


@_attrs_define
class AdminAPIKeyCreate:
    """
    Attributes:
        user_email (str):
        user_display_name (str):
        key_name (str):
        scopes (list[str]):
    """

    user_email: str
    user_display_name: str
    key_name: str
    scopes: list[str]

    def to_dict(self) -> dict[str, Any]:
        user_email = self.user_email

        user_display_name = self.user_display_name

        key_name = self.key_name

        scopes = self.scopes

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "user_email": user_email,
                "user_display_name": user_display_name,
                "key_name": key_name,
                "scopes": scopes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        user_email = d.pop("user_email")

        user_display_name = d.pop("user_display_name")

        key_name = d.pop("key_name")

        scopes = cast(list[str], d.pop("scopes"))

        admin_api_key_create = cls(
            user_email=user_email,
            user_display_name=user_display_name,
            key_name=key_name,
            scopes=scopes,
        )

        return admin_api_key_create
