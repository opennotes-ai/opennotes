from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="UserResponse")


@_attrs_define
class UserResponse:
    """
    Attributes:
        id (UUID):
        username (str):
        email (str):
        full_name (None | str):
        role (str):
        is_active (bool):
        is_superuser (bool):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
    """

    id: UUID
    username: str
    email: str
    full_name: None | str
    role: str
    is_active: bool
    is_superuser: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        username = self.username

        email = self.email

        full_name: None | str
        full_name = self.full_name

        role = self.role

        is_active = self.is_active

        is_superuser = self.is_superuser

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "username": username,
                "email": email,
                "full_name": full_name,
                "role": role,
                "is_active": is_active,
                "is_superuser": is_superuser,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        username = d.pop("username")

        email = d.pop("email")

        def _parse_full_name(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        full_name = _parse_full_name(d.pop("full_name"))

        role = d.pop("role")

        is_active = d.pop("is_active")

        is_superuser = d.pop("is_superuser")

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        user_response = cls(
            id=id,
            username=username,
            email=email,
            full_name=full_name,
            role=role,
            is_active=is_active,
            is_superuser=is_superuser,
            created_at=created_at,
            updated_at=updated_at,
        )

        user_response.additional_properties = d
        return user_response

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
