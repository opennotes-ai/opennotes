from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.monitored_channel_create_data import MonitoredChannelCreateData


T = TypeVar("T", bound="MonitoredChannelCreateRequest")


@_attrs_define
class MonitoredChannelCreateRequest:
    """JSON:API request body for creating a monitored channel.

    Attributes:
        data (MonitoredChannelCreateData): JSON:API data object for monitored channel creation.
    """

    data: MonitoredChannelCreateData

    def to_dict(self) -> dict[str, Any]:
        data = self.data.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "data": data,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.monitored_channel_create_data import MonitoredChannelCreateData

        d = dict(src_dict)
        data = MonitoredChannelCreateData.from_dict(d.pop("data"))

        monitored_channel_create_request = cls(
            data=data,
        )

        return monitored_channel_create_request
