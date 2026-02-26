from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="WelcomeMessageUpdateResponse")


@_attrs_define
class WelcomeMessageUpdateResponse:
    """Response model for welcome message update.

    Attributes:
        id (UUID): Internal community server UUID
        platform_community_server_id (str): Platform-specific ID (e.g., Discord guild ID)
        welcome_message_id (None | str): Discord message ID of the welcome message
    """

    id: UUID
    platform_community_server_id: str
    welcome_message_id: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        platform_community_server_id = self.platform_community_server_id

        welcome_message_id: None | str
        welcome_message_id = self.welcome_message_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "platform_community_server_id": platform_community_server_id,
                "welcome_message_id": welcome_message_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        platform_community_server_id = d.pop("platform_community_server_id")

        def _parse_welcome_message_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        welcome_message_id = _parse_welcome_message_id(d.pop("welcome_message_id"))

        welcome_message_update_response = cls(
            id=id,
            platform_community_server_id=platform_community_server_id,
            welcome_message_id=welcome_message_id,
        )

        welcome_message_update_response.additional_properties = d
        return welcome_message_update_response

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
