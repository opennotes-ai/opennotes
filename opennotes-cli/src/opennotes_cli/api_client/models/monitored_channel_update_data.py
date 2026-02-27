from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.monitored_channel_update_attributes import (
        MonitoredChannelUpdateAttributes,
    )


T = TypeVar("T", bound="MonitoredChannelUpdateData")


@_attrs_define
class MonitoredChannelUpdateData:
    """JSON:API data object for monitored channel update.

    Attributes:
        type_ (Literal['monitored-channels']): Resource type must be 'monitored-channels'
        id (str): Monitored channel ID
        attributes (MonitoredChannelUpdateAttributes): Attributes for updating a monitored channel via JSON:API.
    """

    type_: Literal["monitored-channels"]
    id: str
    attributes: MonitoredChannelUpdateAttributes

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        id = self.id

        attributes = self.attributes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "id": id,
                "attributes": attributes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.monitored_channel_update_attributes import (
            MonitoredChannelUpdateAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["monitored-channels"], d.pop("type"))
        if type_ != "monitored-channels":
            raise ValueError(
                f"type must match const 'monitored-channels', got '{type_}'"
            )

        id = d.pop("id")

        attributes = MonitoredChannelUpdateAttributes.from_dict(d.pop("attributes"))

        monitored_channel_update_data = cls(
            type_=type_,
            id=id,
            attributes=attributes,
        )

        return monitored_channel_update_data
