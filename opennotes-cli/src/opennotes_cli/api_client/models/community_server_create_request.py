from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.community_server_create_request_platform import (
    CommunityServerCreateRequestPlatform,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.community_server_create_request_settings_type_0 import (
        CommunityServerCreateRequestSettingsType0,
    )


T = TypeVar("T", bound="CommunityServerCreateRequest")


@_attrs_define
class CommunityServerCreateRequest:
    """
    Attributes:
        platform (CommunityServerCreateRequestPlatform): Platform type
        platform_community_server_id (str): Platform-specific identifier
        name (str): Human-readable community server name
        description (None | str | Unset): Optional community description
        settings (CommunityServerCreateRequestSettingsType0 | None | Unset): Community-specific settings
        is_active (bool | Unset): Whether the community server is active Default: True.
        is_public (bool | Unset): Whether the community server is publicly visible Default: True.
    """

    platform: CommunityServerCreateRequestPlatform
    platform_community_server_id: str
    name: str
    description: None | str | Unset = UNSET
    settings: CommunityServerCreateRequestSettingsType0 | None | Unset = UNSET
    is_active: bool | Unset = True
    is_public: bool | Unset = True

    def to_dict(self) -> dict[str, Any]:
        from ..models.community_server_create_request_settings_type_0 import (
            CommunityServerCreateRequestSettingsType0,
        )

        platform = self.platform.value

        platform_community_server_id = self.platform_community_server_id

        name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        settings: dict[str, Any] | None | Unset
        if isinstance(self.settings, Unset):
            settings = UNSET
        elif isinstance(self.settings, CommunityServerCreateRequestSettingsType0):
            settings = self.settings.to_dict()
        else:
            settings = self.settings

        is_active = self.is_active

        is_public = self.is_public

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "platform": platform,
                "platform_community_server_id": platform_community_server_id,
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if settings is not UNSET:
            field_dict["settings"] = settings
        if is_active is not UNSET:
            field_dict["is_active"] = is_active
        if is_public is not UNSET:
            field_dict["is_public"] = is_public

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.community_server_create_request_settings_type_0 import (
            CommunityServerCreateRequestSettingsType0,
        )

        d = dict(src_dict)
        platform = CommunityServerCreateRequestPlatform(d.pop("platform"))

        platform_community_server_id = d.pop("platform_community_server_id")

        name = d.pop("name")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_settings(
            data: object,
        ) -> CommunityServerCreateRequestSettingsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                settings_type_0 = CommunityServerCreateRequestSettingsType0.from_dict(
                    data
                )

                return settings_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CommunityServerCreateRequestSettingsType0 | None | Unset, data)

        settings = _parse_settings(d.pop("settings", UNSET))

        is_active = d.pop("is_active", UNSET)

        is_public = d.pop("is_public", UNSET)

        community_server_create_request = cls(
            platform=platform,
            platform_community_server_id=platform_community_server_id,
            name=name,
            description=description,
            settings=settings,
            is_active=is_active,
            is_public=is_public,
        )

        return community_server_create_request
