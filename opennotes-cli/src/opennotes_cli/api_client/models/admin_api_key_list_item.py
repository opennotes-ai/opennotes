from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="AdminAPIKeyListItem")


@_attrs_define
class AdminAPIKeyListItem:
    """
    Attributes:
        id (UUID):
        name (str):
        user_email (str):
        user_display_name (str):
        created_at (datetime.datetime):
        is_active (bool):
        key_prefix (None | str | Unset):
        scopes (list[str] | None | Unset):
        expires_at (datetime.datetime | None | Unset):
    """

    id: UUID
    name: str
    user_email: str
    user_display_name: str
    created_at: datetime.datetime
    is_active: bool
    key_prefix: None | str | Unset = UNSET
    scopes: list[str] | None | Unset = UNSET
    expires_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        name = self.name

        user_email = self.user_email

        user_display_name = self.user_display_name

        created_at = self.created_at.isoformat()

        is_active = self.is_active

        key_prefix: None | str | Unset
        if isinstance(self.key_prefix, Unset):
            key_prefix = UNSET
        else:
            key_prefix = self.key_prefix

        scopes: list[str] | None | Unset
        if isinstance(self.scopes, Unset):
            scopes = UNSET
        elif isinstance(self.scopes, list):
            scopes = self.scopes

        else:
            scopes = self.scopes

        expires_at: None | str | Unset
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        elif isinstance(self.expires_at, datetime.datetime):
            expires_at = self.expires_at.isoformat()
        else:
            expires_at = self.expires_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "user_email": user_email,
                "user_display_name": user_display_name,
                "created_at": created_at,
                "is_active": is_active,
            }
        )
        if key_prefix is not UNSET:
            field_dict["key_prefix"] = key_prefix
        if scopes is not UNSET:
            field_dict["scopes"] = scopes
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        name = d.pop("name")

        user_email = d.pop("user_email")

        user_display_name = d.pop("user_display_name")

        created_at = isoparse(d.pop("created_at"))

        is_active = d.pop("is_active")

        def _parse_key_prefix(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        key_prefix = _parse_key_prefix(d.pop("key_prefix", UNSET))

        def _parse_scopes(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                scopes_type_0 = cast(list[str], data)

                return scopes_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        scopes = _parse_scopes(d.pop("scopes", UNSET))

        def _parse_expires_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                expires_at_type_0 = isoparse(data)

                return expires_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        expires_at = _parse_expires_at(d.pop("expires_at", UNSET))

        admin_api_key_list_item = cls(
            id=id,
            name=name,
            user_email=user_email,
            user_display_name=user_display_name,
            created_at=created_at,
            is_active=is_active,
            key_prefix=key_prefix,
            scopes=scopes,
            expires_at=expires_at,
        )

        admin_api_key_list_item.additional_properties = d
        return admin_api_key_list_item

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
