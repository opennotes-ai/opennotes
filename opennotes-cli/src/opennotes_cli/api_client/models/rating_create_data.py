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
    from ..models.rating_create_attributes import RatingCreateAttributes


T = TypeVar("T", bound="RatingCreateData")


@_attrs_define
class RatingCreateData:
    """JSON:API data object for rating creation.

    Attributes:
        type_ (Literal['ratings']): Resource type must be 'ratings'
        attributes (RatingCreateAttributes): Attributes for creating a rating via JSON:API.
    """

    type_: Literal["ratings"]
    attributes: RatingCreateAttributes

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
        from ..models.rating_create_attributes import RatingCreateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["ratings"], d.pop("type"))
        if type_ != "ratings":
            raise ValueError(f"type must match const 'ratings', got '{type_}'")

        attributes = RatingCreateAttributes.from_dict(d.pop("attributes"))

        rating_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return rating_create_data
