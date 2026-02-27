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
    from ..models.similarity_search_create_attributes import (
        SimilaritySearchCreateAttributes,
    )


T = TypeVar("T", bound="SimilaritySearchCreateData")


@_attrs_define
class SimilaritySearchCreateData:
    """JSON:API data object for similarity search.

    Attributes:
        type_ (Literal['similarity-searches']): Resource type must be 'similarity-searches'
        attributes (SimilaritySearchCreateAttributes): Attributes for performing a similarity search via JSON:API.
    """

    type_: Literal["similarity-searches"]
    attributes: SimilaritySearchCreateAttributes

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
        from ..models.similarity_search_create_attributes import (
            SimilaritySearchCreateAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["similarity-searches"], d.pop("type"))
        if type_ != "similarity-searches":
            raise ValueError(
                f"type must match const 'similarity-searches', got '{type_}'"
            )

        attributes = SimilaritySearchCreateAttributes.from_dict(d.pop("attributes"))

        similarity_search_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return similarity_search_create_data
