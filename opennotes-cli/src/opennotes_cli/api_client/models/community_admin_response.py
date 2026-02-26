from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.admin_source import AdminSource
from ..types import UNSET, Unset

T = TypeVar("T", bound="CommunityAdminResponse")


@_attrs_define
class CommunityAdminResponse:
    """Response schema for community admin information.

    Attributes:
        profile_id (UUID): User profile identifier
        display_name (str): User's display name
        discord_id (str): User's Discord ID
        admin_sources (list[AdminSource]): Sources of admin privileges (can have multiple)
        joined_at (datetime.datetime): When the user joined the community
        avatar_url (None | str | Unset): URL to user's avatar image
        is_opennotes_admin (bool | Unset): Whether user is an Open Notes platform admin Default: False.
        community_role (str | Unset): User's role in the community Default: 'member'.
    """

    profile_id: UUID
    display_name: str
    discord_id: str
    admin_sources: list[AdminSource]
    joined_at: datetime.datetime
    avatar_url: None | str | Unset = UNSET
    is_opennotes_admin: bool | Unset = False
    community_role: str | Unset = "member"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        profile_id = str(self.profile_id)

        display_name = self.display_name

        discord_id = self.discord_id

        admin_sources = []
        for admin_sources_item_data in self.admin_sources:
            admin_sources_item = admin_sources_item_data.value
            admin_sources.append(admin_sources_item)

        joined_at = self.joined_at.isoformat()

        avatar_url: None | str | Unset
        if isinstance(self.avatar_url, Unset):
            avatar_url = UNSET
        else:
            avatar_url = self.avatar_url

        is_opennotes_admin = self.is_opennotes_admin

        community_role = self.community_role

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "profile_id": profile_id,
                "display_name": display_name,
                "discord_id": discord_id,
                "admin_sources": admin_sources,
                "joined_at": joined_at,
            }
        )
        if avatar_url is not UNSET:
            field_dict["avatar_url"] = avatar_url
        if is_opennotes_admin is not UNSET:
            field_dict["is_opennotes_admin"] = is_opennotes_admin
        if community_role is not UNSET:
            field_dict["community_role"] = community_role

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        profile_id = UUID(d.pop("profile_id"))

        display_name = d.pop("display_name")

        discord_id = d.pop("discord_id")

        admin_sources = []
        _admin_sources = d.pop("admin_sources")
        for admin_sources_item_data in _admin_sources:
            admin_sources_item = AdminSource(admin_sources_item_data)

            admin_sources.append(admin_sources_item)

        joined_at = isoparse(d.pop("joined_at"))

        def _parse_avatar_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        avatar_url = _parse_avatar_url(d.pop("avatar_url", UNSET))

        is_opennotes_admin = d.pop("is_opennotes_admin", UNSET)

        community_role = d.pop("community_role", UNSET)

        community_admin_response = cls(
            profile_id=profile_id,
            display_name=display_name,
            discord_id=discord_id,
            admin_sources=admin_sources,
            joined_at=joined_at,
            avatar_url=avatar_url,
            is_opennotes_admin=is_opennotes_admin,
            community_role=community_role,
        )

        community_admin_response.additional_properties = d
        return community_admin_response

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
