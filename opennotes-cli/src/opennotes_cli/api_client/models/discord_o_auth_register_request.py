from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="DiscordOAuthRegisterRequest")


@_attrs_define
class DiscordOAuthRegisterRequest:
    """Request schema for Discord OAuth2 registration.

    Attributes:
        code (str): OAuth2 authorization code from Discord
        state (str): OAuth2 state parameter for CSRF protection (must match state from init)
        display_name (str): User's desired display name
        avatar_url (None | str | Unset): URL to user's avatar image (optional override)
    """

    code: str
    state: str
    display_name: str
    avatar_url: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        state = self.state

        display_name = self.display_name

        avatar_url: None | str | Unset
        if isinstance(self.avatar_url, Unset):
            avatar_url = UNSET
        else:
            avatar_url = self.avatar_url

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "code": code,
                "state": state,
                "display_name": display_name,
            }
        )
        if avatar_url is not UNSET:
            field_dict["avatar_url"] = avatar_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = d.pop("code")

        state = d.pop("state")

        display_name = d.pop("display_name")

        def _parse_avatar_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        avatar_url = _parse_avatar_url(d.pop("avatar_url", UNSET))

        discord_o_auth_register_request = cls(
            code=code,
            state=state,
            display_name=display_name,
            avatar_url=avatar_url,
        )

        return discord_o_auth_register_request
