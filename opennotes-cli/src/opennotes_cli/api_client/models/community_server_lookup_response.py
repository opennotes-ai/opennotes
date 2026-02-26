from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="CommunityServerLookupResponse")


@_attrs_define
class CommunityServerLookupResponse:
    """Response model for community server lookup.

    Attributes:
        id (UUID): Internal community server UUID
        platform (str): Platform type (e.g., 'discord')
        platform_community_server_id (str): Platform-specific ID (e.g., Discord guild ID)
        name (str): Community server name
        is_active (bool): Whether the community server is active
        flashpoint_detection_enabled (bool): Whether flashpoint detection is enabled for this community
    """

    id: UUID
    platform: str
    platform_community_server_id: str
    name: str
    is_active: bool
    flashpoint_detection_enabled: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        platform = self.platform

        platform_community_server_id = self.platform_community_server_id

        name = self.name

        is_active = self.is_active

        flashpoint_detection_enabled = self.flashpoint_detection_enabled

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "platform": platform,
                "platform_community_server_id": platform_community_server_id,
                "name": name,
                "is_active": is_active,
                "flashpoint_detection_enabled": flashpoint_detection_enabled,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        platform = d.pop("platform")

        platform_community_server_id = d.pop("platform_community_server_id")

        name = d.pop("name")

        is_active = d.pop("is_active")

        flashpoint_detection_enabled = d.pop("flashpoint_detection_enabled")

        community_server_lookup_response = cls(
            id=id,
            platform=platform,
            platform_community_server_id=platform_community_server_id,
            name=name,
            is_active=is_active,
            flashpoint_detection_enabled=flashpoint_detection_enabled,
        )

        community_server_lookup_response.additional_properties = d
        return community_server_lookup_response

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
