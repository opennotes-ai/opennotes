from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="ProfileAttributes")


@_attrs_define
class ProfileAttributes:
    """Profile attributes for JSON:API resource.

    Attributes:
        display_name (str):
        avatar_url (None | str | Unset):
        bio (None | str | Unset):
        reputation (int | Unset):  Default: 0.
        is_opennotes_admin (bool | Unset):  Default: False.
        is_human (bool | Unset):  Default: True.
        is_active (bool | Unset):  Default: True.
        is_banned (bool | Unset):  Default: False.
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
    """

    display_name: str
    avatar_url: None | str | Unset = UNSET
    bio: None | str | Unset = UNSET
    reputation: int | Unset = 0
    is_opennotes_admin: bool | Unset = False
    is_human: bool | Unset = True
    is_active: bool | Unset = True
    is_banned: bool | Unset = False
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        display_name = self.display_name

        avatar_url: None | str | Unset
        if isinstance(self.avatar_url, Unset):
            avatar_url = UNSET
        else:
            avatar_url = self.avatar_url

        bio: None | str | Unset
        if isinstance(self.bio, Unset):
            bio = UNSET
        else:
            bio = self.bio

        reputation = self.reputation

        is_opennotes_admin = self.is_opennotes_admin

        is_human = self.is_human

        is_active = self.is_active

        is_banned = self.is_banned

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "display_name": display_name,
            }
        )
        if avatar_url is not UNSET:
            field_dict["avatar_url"] = avatar_url
        if bio is not UNSET:
            field_dict["bio"] = bio
        if reputation is not UNSET:
            field_dict["reputation"] = reputation
        if is_opennotes_admin is not UNSET:
            field_dict["is_opennotes_admin"] = is_opennotes_admin
        if is_human is not UNSET:
            field_dict["is_human"] = is_human
        if is_active is not UNSET:
            field_dict["is_active"] = is_active
        if is_banned is not UNSET:
            field_dict["is_banned"] = is_banned
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        display_name = d.pop("display_name")

        def _parse_avatar_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        avatar_url = _parse_avatar_url(d.pop("avatar_url", UNSET))

        def _parse_bio(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bio = _parse_bio(d.pop("bio", UNSET))

        reputation = d.pop("reputation", UNSET)

        is_opennotes_admin = d.pop("is_opennotes_admin", UNSET)

        is_human = d.pop("is_human", UNSET)

        is_active = d.pop("is_active", UNSET)

        is_banned = d.pop("is_banned", UNSET)

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        profile_attributes = cls(
            display_name=display_name,
            avatar_url=avatar_url,
            bio=bio,
            reputation=reputation,
            is_opennotes_admin=is_opennotes_admin,
            is_human=is_human,
            is_active=is_active,
            is_banned=is_banned,
            created_at=created_at,
            updated_at=updated_at,
        )

        profile_attributes.additional_properties = d
        return profile_attributes

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
