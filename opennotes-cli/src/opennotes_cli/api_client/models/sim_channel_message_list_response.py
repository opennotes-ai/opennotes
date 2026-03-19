from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.sim_channel_message_list_meta import SimChannelMessageListMeta
    from ..models.sim_channel_message_list_response_jsonapi import (
        SimChannelMessageListResponseJsonapi,
    )
    from ..models.sim_channel_message_resource import SimChannelMessageResource


T = TypeVar("T", bound="SimChannelMessageListResponse")


@_attrs_define
class SimChannelMessageListResponse:
    """
    Attributes:
        data (list[SimChannelMessageResource]):
        meta (SimChannelMessageListMeta):
        jsonapi (SimChannelMessageListResponseJsonapi | Unset):
    """

    data: list[SimChannelMessageResource]
    meta: SimChannelMessageListMeta
    jsonapi: SimChannelMessageListResponseJsonapi | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = []
        for data_item_data in self.data:
            data_item = data_item_data.to_dict()
            data.append(data_item)

        meta = self.meta.to_dict()

        jsonapi: dict[str, Any] | Unset = UNSET
        if not isinstance(self.jsonapi, Unset):
            jsonapi = self.jsonapi.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data": data,
                "meta": meta,
            }
        )
        if jsonapi is not UNSET:
            field_dict["jsonapi"] = jsonapi

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.sim_channel_message_list_meta import SimChannelMessageListMeta
        from ..models.sim_channel_message_list_response_jsonapi import (
            SimChannelMessageListResponseJsonapi,
        )
        from ..models.sim_channel_message_resource import SimChannelMessageResource

        d = dict(src_dict)
        data = []
        _data = d.pop("data")
        for data_item_data in _data:
            data_item = SimChannelMessageResource.from_dict(data_item_data)

            data.append(data_item)

        meta = SimChannelMessageListMeta.from_dict(d.pop("meta"))

        _jsonapi = d.pop("jsonapi", UNSET)
        jsonapi: SimChannelMessageListResponseJsonapi | Unset
        if isinstance(_jsonapi, Unset):
            jsonapi = UNSET
        else:
            jsonapi = SimChannelMessageListResponseJsonapi.from_dict(_jsonapi)

        sim_channel_message_list_response = cls(
            data=data,
            meta=meta,
            jsonapi=jsonapi,
        )

        sim_channel_message_list_response.additional_properties = d
        return sim_channel_message_list_response

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
