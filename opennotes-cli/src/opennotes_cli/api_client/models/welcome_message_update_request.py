from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

T = TypeVar("T", bound="WelcomeMessageUpdateRequest")


@_attrs_define
class WelcomeMessageUpdateRequest:
    """Request model for updating welcome message ID.

    Attributes:
        welcome_message_id (None | str): Discord message ID of the welcome message, or null to clear
    """

    welcome_message_id: None | str

    def to_dict(self) -> dict[str, Any]:
        welcome_message_id: None | str
        welcome_message_id = self.welcome_message_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "welcome_message_id": welcome_message_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_welcome_message_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        welcome_message_id = _parse_welcome_message_id(d.pop("welcome_message_id"))

        welcome_message_update_request = cls(
            welcome_message_id=welcome_message_id,
        )

        return welcome_message_update_request
