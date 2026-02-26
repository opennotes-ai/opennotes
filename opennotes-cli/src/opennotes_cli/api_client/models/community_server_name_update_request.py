from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.community_server_name_update_request_server_stats_type_0 import (
        CommunityServerNameUpdateRequestServerStatsType0,
    )


T = TypeVar("T", bound="CommunityServerNameUpdateRequest")


@_attrs_define
class CommunityServerNameUpdateRequest:
    """Request model for updating community server name and stats.

    Attributes:
        name (str): Human-readable name for the community server
        server_stats (CommunityServerNameUpdateRequestServerStatsType0 | None | Unset): Aggregate server statistics
            (e.g., member_count)
    """

    name: str
    server_stats: CommunityServerNameUpdateRequestServerStatsType0 | None | Unset = (
        UNSET
    )

    def to_dict(self) -> dict[str, Any]:
        from ..models.community_server_name_update_request_server_stats_type_0 import (
            CommunityServerNameUpdateRequestServerStatsType0,
        )

        name = self.name

        server_stats: dict[str, Any] | None | Unset
        if isinstance(self.server_stats, Unset):
            server_stats = UNSET
        elif isinstance(
            self.server_stats, CommunityServerNameUpdateRequestServerStatsType0
        ):
            server_stats = self.server_stats.to_dict()
        else:
            server_stats = self.server_stats

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
            }
        )
        if server_stats is not UNSET:
            field_dict["server_stats"] = server_stats

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.community_server_name_update_request_server_stats_type_0 import (
            CommunityServerNameUpdateRequestServerStatsType0,
        )

        d = dict(src_dict)
        name = d.pop("name")

        def _parse_server_stats(
            data: object,
        ) -> CommunityServerNameUpdateRequestServerStatsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                server_stats_type_0 = (
                    CommunityServerNameUpdateRequestServerStatsType0.from_dict(data)
                )

                return server_stats_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                CommunityServerNameUpdateRequestServerStatsType0 | None | Unset, data
            )

        server_stats = _parse_server_stats(d.pop("server_stats", UNSET))

        community_server_name_update_request = cls(
            name=name,
            server_stats=server_stats,
        )

        return community_server_name_update_request
