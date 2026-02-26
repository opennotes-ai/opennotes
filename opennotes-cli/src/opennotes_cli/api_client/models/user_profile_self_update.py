from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="UserProfileSelfUpdate")


@_attrs_define
class UserProfileSelfUpdate:
    """Schema for users updating their own profile (self-service).

    Security: This schema only exposes user-editable fields.
    Privileged fields (role, is_opennotes_admin, is_banned, etc.) are
    intentionally excluded to prevent privilege escalation attacks.

    Use UserProfileAdminUpdate for admin operations on user profiles.

        Attributes:
            display_name (None | str | Unset): User's display name
            avatar_url (None | str | Unset): URL to user's avatar image
            bio (None | str | Unset): User biography/description
    """

    display_name: None | str | Unset = UNSET
    avatar_url: None | str | Unset = UNSET
    bio: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        display_name: None | str | Unset
        if isinstance(self.display_name, Unset):
            display_name = UNSET
        else:
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

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if display_name is not UNSET:
            field_dict["display_name"] = display_name
        if avatar_url is not UNSET:
            field_dict["avatar_url"] = avatar_url
        if bio is not UNSET:
            field_dict["bio"] = bio

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_display_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        display_name = _parse_display_name(d.pop("display_name", UNSET))

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

        user_profile_self_update = cls(
            display_name=display_name,
            avatar_url=avatar_url,
            bio=bio,
        )

        return user_profile_self_update
