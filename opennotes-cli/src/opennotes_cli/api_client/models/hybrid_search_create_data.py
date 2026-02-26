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
    from ..models.hybrid_search_create_attributes import HybridSearchCreateAttributes


T = TypeVar("T", bound="HybridSearchCreateData")


@_attrs_define
class HybridSearchCreateData:
    """JSON:API data object for hybrid search.

    Attributes:
        type_ (Literal['hybrid-searches']): Resource type must be 'hybrid-searches'
        attributes (HybridSearchCreateAttributes): Attributes for performing a hybrid search via JSON:API.
    """

    type_: Literal["hybrid-searches"]
    attributes: HybridSearchCreateAttributes

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
        from ..models.hybrid_search_create_attributes import (
            HybridSearchCreateAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["hybrid-searches"], d.pop("type"))
        if type_ != "hybrid-searches":
            raise ValueError(f"type must match const 'hybrid-searches', got '{type_}'")

        attributes = HybridSearchCreateAttributes.from_dict(d.pop("attributes"))

        hybrid_search_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return hybrid_search_create_data
