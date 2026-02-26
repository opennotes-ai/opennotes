from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.community_config_response_config import CommunityConfigResponseConfig


T = TypeVar("T", bound="CommunityConfigResponse")


@_attrs_define
class CommunityConfigResponse:
    """
    Attributes:
        community_server_id (UUID):
        config (CommunityConfigResponseConfig | Unset): Community server configuration key-value pairs
    """

    community_server_id: UUID
    config: CommunityConfigResponseConfig | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        community_server_id = str(self.community_server_id)

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "community_server_id": community_server_id,
            }
        )
        if config is not UNSET:
            field_dict["config"] = config

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.community_config_response_config import (
            CommunityConfigResponseConfig,
        )

        d = dict(src_dict)
        community_server_id = UUID(d.pop("community_server_id"))

        _config = d.pop("config", UNSET)
        config: CommunityConfigResponseConfig | Unset
        if isinstance(_config, Unset):
            config = UNSET
        else:
            config = CommunityConfigResponseConfig.from_dict(_config)

        community_config_response = cls(
            community_server_id=community_server_id,
            config=config,
        )

        community_config_response.additional_properties = d
        return community_config_response

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
