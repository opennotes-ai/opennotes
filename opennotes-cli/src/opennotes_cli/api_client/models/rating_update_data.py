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
    from ..models.rating_update_attributes import RatingUpdateAttributes


T = TypeVar("T", bound="RatingUpdateData")


@_attrs_define
class RatingUpdateData:
    """JSON:API data object for rating update.

    Attributes:
        type_ (Literal['ratings']): Resource type must be 'ratings'
        id (str): Rating ID
        attributes (RatingUpdateAttributes): Attributes for updating a rating via JSON:API.
    """

    type_: Literal["ratings"]
    id: str
    attributes: RatingUpdateAttributes

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
        from ..models.rating_update_attributes import RatingUpdateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["ratings"], d.pop("type"))
        if type_ != "ratings":
            raise ValueError(f"type must match const 'ratings', got '{type_}'")

        id = d.pop("id")

        attributes = RatingUpdateAttributes.from_dict(d.pop("attributes"))

        rating_update_data = cls(
            type_=type_,
            id=id,
            attributes=attributes,
        )

        return rating_update_data
