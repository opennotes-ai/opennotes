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
    from ..models.previously_seen_check_attributes import PreviouslySeenCheckAttributes


T = TypeVar("T", bound="PreviouslySeenCheckData")


@_attrs_define
class PreviouslySeenCheckData:
    """JSON:API data object for previously seen message check.

    Attributes:
        type_ (Literal['previously-seen-check']): Resource type must be 'previously-seen-check'
        attributes (PreviouslySeenCheckAttributes): Attributes for checking previously seen messages via JSON:API.
    """

    type_: Literal["previously-seen-check"]
    attributes: PreviouslySeenCheckAttributes

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
        from ..models.previously_seen_check_attributes import (
            PreviouslySeenCheckAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["previously-seen-check"], d.pop("type"))
        if type_ != "previously-seen-check":
            raise ValueError(
                f"type must match const 'previously-seen-check', got '{type_}'"
            )

        attributes = PreviouslySeenCheckAttributes.from_dict(d.pop("attributes"))

        previously_seen_check_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return previously_seen_check_data
