from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="RefreshTokenRequest")


@_attrs_define
class RefreshTokenRequest:
    """Request body for refresh token endpoint.

    Attributes:
        refresh_token (str): The refresh token to use for getting a new access token
    """

    refresh_token: str

    def to_dict(self) -> dict[str, Any]:
        refresh_token = self.refresh_token

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "refresh_token": refresh_token,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        refresh_token = d.pop("refresh_token")

        refresh_token_request = cls(
            refresh_token=refresh_token,
        )

        return refresh_token_request
