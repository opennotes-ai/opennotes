from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="DiscordOAuthInitResponse")


@_attrs_define
class DiscordOAuthInitResponse:
    """Response schema for Discord OAuth2 flow initialization.

    Attributes:
        authorization_url (str): Discord OAuth2 authorization URL to redirect user to
        state (str): OAuth2 state parameter for CSRF protection (store for callback validation)
    """

    authorization_url: str
    state: str

    def to_dict(self) -> dict[str, Any]:
        authorization_url = self.authorization_url

        state = self.state

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "authorization_url": authorization_url,
                "state": state,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        authorization_url = d.pop("authorization_url")

        state = d.pop("state")

        discord_o_auth_init_response = cls(
            authorization_url=authorization_url,
            state=state,
        )

        return discord_o_auth_init_response
