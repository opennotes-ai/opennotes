from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="DiscordOAuthLoginRequest")


@_attrs_define
class DiscordOAuthLoginRequest:
    """Request schema for Discord OAuth2 login.

    Attributes:
        code (str): OAuth2 authorization code from Discord
        state (str): OAuth2 state parameter for CSRF protection (must match state from init)
    """

    code: str
    state: str

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        state = self.state

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "code": code,
                "state": state,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = d.pop("code")

        state = d.pop("state")

        discord_o_auth_login_request = cls(
            code=code,
            state=state,
        )

        return discord_o_auth_login_request
