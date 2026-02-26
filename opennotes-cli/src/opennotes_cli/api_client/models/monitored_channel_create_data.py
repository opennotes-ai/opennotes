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
    from ..models.monitored_channel_create_attributes import (
        MonitoredChannelCreateAttributes,
    )


T = TypeVar("T", bound="MonitoredChannelCreateData")


@_attrs_define
class MonitoredChannelCreateData:
    """JSON:API data object for monitored channel creation.

    Attributes:
        type_ (Literal['monitored-channels']): Resource type must be 'monitored-channels'
        attributes (MonitoredChannelCreateAttributes): Attributes for creating a monitored channel via JSON:API.
    """

    type_: Literal["monitored-channels"]
    attributes: MonitoredChannelCreateAttributes

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        attributes = self.attributes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "attributes": attributes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.monitored_channel_create_attributes import (
            MonitoredChannelCreateAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["monitored-channels"], d.pop("type"))
        if type_ != "monitored-channels":
            raise ValueError(
                f"type must match const 'monitored-channels', got '{type_}'"
            )

        attributes = MonitoredChannelCreateAttributes.from_dict(d.pop("attributes"))

        monitored_channel_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return monitored_channel_create_data
