from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.community_server_create_response_platform import (
    CommunityServerCreateResponsePlatform,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.community_server_create_response_settings_type_0 import (
        CommunityServerCreateResponseSettingsType0,
    )


T = TypeVar("T", bound="CommunityServerCreateResponse")


@_attrs_define
class CommunityServerCreateResponse:
    """
    Attributes:
        id (UUID): Internal community server UUID
        platform (CommunityServerCreateResponsePlatform): Platform type
        platform_community_server_id (str): Platform-specific identifier
        name (str): Community server name
        is_active (bool): Whether the community server is active
        is_public (bool): Whether the community server is publicly visible
        flashpoint_detection_enabled (bool): Whether flashpoint detection is enabled
        created_at (datetime.datetime): Creation timestamp
        updated_at (datetime.datetime): Last update timestamp
        description (None | str | Unset): Community description
        settings (CommunityServerCreateResponseSettingsType0 | None | Unset): Community-specific settings
    """

    id: UUID
    platform: CommunityServerCreateResponsePlatform
    platform_community_server_id: str
    name: str
    is_active: bool
    is_public: bool
    flashpoint_detection_enabled: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
    description: None | str | Unset = UNSET
    settings: CommunityServerCreateResponseSettingsType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.community_server_create_response_settings_type_0 import (
            CommunityServerCreateResponseSettingsType0,
        )

        id = str(self.id)

        platform = self.platform.value

        platform_community_server_id = self.platform_community_server_id

        name = self.name

        is_active = self.is_active

        is_public = self.is_public

        flashpoint_detection_enabled = self.flashpoint_detection_enabled

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        settings: dict[str, Any] | None | Unset
        if isinstance(self.settings, Unset):
            settings = UNSET
        elif isinstance(self.settings, CommunityServerCreateResponseSettingsType0):
            settings = self.settings.to_dict()
        else:
            settings = self.settings

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "platform": platform,
                "platform_community_server_id": platform_community_server_id,
                "name": name,
                "is_active": is_active,
                "is_public": is_public,
                "flashpoint_detection_enabled": flashpoint_detection_enabled,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if settings is not UNSET:
            field_dict["settings"] = settings

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.community_server_create_response_settings_type_0 import (
            CommunityServerCreateResponseSettingsType0,
        )

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        platform = CommunityServerCreateResponsePlatform(d.pop("platform"))

        platform_community_server_id = d.pop("platform_community_server_id")

        name = d.pop("name")

        is_active = d.pop("is_active")

        is_public = d.pop("is_public")

        flashpoint_detection_enabled = d.pop("flashpoint_detection_enabled")

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_settings(
            data: object,
        ) -> CommunityServerCreateResponseSettingsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                settings_type_0 = CommunityServerCreateResponseSettingsType0.from_dict(
                    data
                )

                return settings_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CommunityServerCreateResponseSettingsType0 | None | Unset, data)

        settings = _parse_settings(d.pop("settings", UNSET))

        community_server_create_response = cls(
            id=id,
            platform=platform,
            platform_community_server_id=platform_community_server_id,
            name=name,
            is_active=is_active,
            is_public=is_public,
            flashpoint_detection_enabled=flashpoint_detection_enabled,
            created_at=created_at,
            updated_at=updated_at,
            description=description,
            settings=settings,
        )

        community_server_create_response.additional_properties = d
        return community_server_create_response

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
