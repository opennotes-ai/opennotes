from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="UserCreate")


@_attrs_define
class UserCreate:
    """
    Attributes:
        username (str):
        email (str):
        password (str):
        full_name (None | str | Unset):
    """

    username: str
    email: str
    password: str
    full_name: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        username = self.username

        email = self.email

        password = self.password

        full_name: None | str | Unset
        if isinstance(self.full_name, Unset):
            full_name = UNSET
        else:
            full_name = self.full_name

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "username": username,
                "email": email,
                "password": password,
            }
        )
        if full_name is not UNSET:
            field_dict["full_name"] = full_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        username = d.pop("username")

        email = d.pop("email")

        password = d.pop("password")

        def _parse_full_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        full_name = _parse_full_name(d.pop("full_name", UNSET))

        user_create = cls(
            username=username,
            email=email,
            password=password,
            full_name=full_name,
        )

        return user_create
