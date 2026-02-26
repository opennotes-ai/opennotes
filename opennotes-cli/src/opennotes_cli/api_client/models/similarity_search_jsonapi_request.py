from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.similarity_search_create_data import SimilaritySearchCreateData


T = TypeVar("T", bound="SimilaritySearchJSONAPIRequest")


@_attrs_define
class SimilaritySearchJSONAPIRequest:
    """JSON:API request body for performing a similarity search.

    Attributes:
        data (SimilaritySearchCreateData): JSON:API data object for similarity search.
    """

    data: SimilaritySearchCreateData

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
        from ..models.similarity_search_create_data import SimilaritySearchCreateData

        d = dict(src_dict)
        data = SimilaritySearchCreateData.from_dict(d.pop("data"))

        similarity_search_jsonapi_request = cls(
            data=data,
        )

        return similarity_search_jsonapi_request
