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
    from ..models.set_rating_attributes import SetRatingAttributes


T = TypeVar("T", bound="SetRatingData")


@_attrs_define
class SetRatingData:
    """JSON:API data object for setting rating.

    Attributes:
        type_ (Literal['fact-check-candidates']): Resource type must be 'fact-check-candidates'
        attributes (SetRatingAttributes): Attributes for setting rating on a candidate via JSON:API.
    """

    type_: Literal["fact-check-candidates"]
    attributes: SetRatingAttributes

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
        from ..models.set_rating_attributes import SetRatingAttributes

        d = dict(src_dict)
        type_ = cast(Literal["fact-check-candidates"], d.pop("type"))
        if type_ != "fact-check-candidates":
            raise ValueError(
                f"type must match const 'fact-check-candidates', got '{type_}'"
            )

        attributes = SetRatingAttributes.from_dict(d.pop("attributes"))

        set_rating_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return set_rating_data
