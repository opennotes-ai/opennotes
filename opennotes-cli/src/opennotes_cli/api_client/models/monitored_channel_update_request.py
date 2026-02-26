from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.monitored_channel_update_data import MonitoredChannelUpdateData


T = TypeVar("T", bound="MonitoredChannelUpdateRequest")


@_attrs_define
class MonitoredChannelUpdateRequest:
    """JSON:API request body for updating a monitored channel.

    Attributes:
        data (MonitoredChannelUpdateData): JSON:API data object for monitored channel update.
    """

    data: MonitoredChannelUpdateData

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
        from ..models.monitored_channel_update_data import MonitoredChannelUpdateData

        d = dict(src_dict)
        data = MonitoredChannelUpdateData.from_dict(d.pop("data"))

        monitored_channel_update_request = cls(
            data=data,
        )

        return monitored_channel_update_request
