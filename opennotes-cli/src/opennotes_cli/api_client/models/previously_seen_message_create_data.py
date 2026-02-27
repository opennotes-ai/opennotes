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
    from ..models.previously_seen_message_create_attributes import (
        PreviouslySeenMessageCreateAttributes,
    )


T = TypeVar("T", bound="PreviouslySeenMessageCreateData")


@_attrs_define
class PreviouslySeenMessageCreateData:
    """JSON:API data object for previously seen message creation.

    Attributes:
        type_ (Literal['previously-seen-messages']): Resource type must be 'previously-seen-messages'
        attributes (PreviouslySeenMessageCreateAttributes): Attributes for creating a previously seen message via
            JSON:API.
    """

    type_: Literal["previously-seen-messages"]
    attributes: PreviouslySeenMessageCreateAttributes

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
        from ..models.previously_seen_message_create_attributes import (
            PreviouslySeenMessageCreateAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["previously-seen-messages"], d.pop("type"))
        if type_ != "previously-seen-messages":
            raise ValueError(
                f"type must match const 'previously-seen-messages', got '{type_}'"
            )

        attributes = PreviouslySeenMessageCreateAttributes.from_dict(
            d.pop("attributes")
        )

        previously_seen_message_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return previously_seen_message_create_data
