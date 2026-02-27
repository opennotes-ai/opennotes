from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="AddCommunityAdminRequest")


@_attrs_define
class AddCommunityAdminRequest:
    """Request schema for adding a community admin.

    Attributes:
        user_discord_id (str): Discord ID of the user to promote to admin
        username (None | str | Unset): Discord username (for auto-creating profile if user doesn't exist)
        display_name (None | str | Unset): Display name (for auto-creating profile if user doesn't exist)
        avatar_url (None | str | Unset): Avatar URL (for auto-creating profile if user doesn't exist)
    """

    user_discord_id: str
    username: None | str | Unset = UNSET
    display_name: None | str | Unset = UNSET
    avatar_url: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        user_discord_id = self.user_discord_id

        username: None | str | Unset
        if isinstance(self.username, Unset):
            username = UNSET
        else:
            username = self.username

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

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "user_discord_id": user_discord_id,
            }
        )
        if username is not UNSET:
            field_dict["username"] = username
        if display_name is not UNSET:
            field_dict["display_name"] = display_name
        if avatar_url is not UNSET:
            field_dict["avatar_url"] = avatar_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        user_discord_id = d.pop("user_discord_id")

        def _parse_username(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        username = _parse_username(d.pop("username", UNSET))

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

        add_community_admin_request = cls(
            user_discord_id=user_discord_id,
            username=username,
            display_name=display_name,
            avatar_url=avatar_url,
        )

        return add_community_admin_request
