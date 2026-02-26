from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.community_server_name_update_response_server_stats_type_0 import (
        CommunityServerNameUpdateResponseServerStatsType0,
    )


T = TypeVar("T", bound="CommunityServerNameUpdateResponse")


@_attrs_define
class CommunityServerNameUpdateResponse:
    """Response model for community server name update.

    Attributes:
        id (UUID): Internal community server UUID
        platform_community_server_id (str): Platform-specific ID (e.g., Discord guild ID)
        name (str): Updated community server name
        server_stats (CommunityServerNameUpdateResponseServerStatsType0 | None | Unset): Aggregate server statistics
    """

    id: UUID
    platform_community_server_id: str
    name: str
    server_stats: CommunityServerNameUpdateResponseServerStatsType0 | None | Unset = (
        UNSET
    )
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.community_server_name_update_response_server_stats_type_0 import (
            CommunityServerNameUpdateResponseServerStatsType0,
        )

        id = str(self.id)

        platform_community_server_id = self.platform_community_server_id

        name = self.name

        server_stats: dict[str, Any] | None | Unset
        if isinstance(self.server_stats, Unset):
            server_stats = UNSET
        elif isinstance(
            self.server_stats, CommunityServerNameUpdateResponseServerStatsType0
        ):
            server_stats = self.server_stats.to_dict()
        else:
            server_stats = self.server_stats

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "platform_community_server_id": platform_community_server_id,
                "name": name,
            }
        )
        if server_stats is not UNSET:
            field_dict["server_stats"] = server_stats

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.community_server_name_update_response_server_stats_type_0 import (
            CommunityServerNameUpdateResponseServerStatsType0,
        )

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        platform_community_server_id = d.pop("platform_community_server_id")

        name = d.pop("name")

        def _parse_server_stats(
            data: object,
        ) -> CommunityServerNameUpdateResponseServerStatsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                server_stats_type_0 = (
                    CommunityServerNameUpdateResponseServerStatsType0.from_dict(data)
                )

                return server_stats_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                CommunityServerNameUpdateResponseServerStatsType0 | None | Unset, data
            )

        server_stats = _parse_server_stats(d.pop("server_stats", UNSET))

        community_server_name_update_response = cls(
            id=id,
            platform_community_server_id=platform_community_server_id,
            name=name,
            server_stats=server_stats,
        )

        community_server_name_update_response.additional_properties = d
        return community_server_name_update_response

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
