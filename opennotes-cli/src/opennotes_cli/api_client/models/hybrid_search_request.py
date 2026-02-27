from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.hybrid_search_create_data import HybridSearchCreateData


T = TypeVar("T", bound="HybridSearchRequest")


@_attrs_define
class HybridSearchRequest:
    """JSON:API request body for performing a hybrid search.

    Attributes:
        data (HybridSearchCreateData): JSON:API data object for hybrid search.
    """

    data: HybridSearchCreateData

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
        from ..models.hybrid_search_create_data import HybridSearchCreateData

        d = dict(src_dict)
        data = HybridSearchCreateData.from_dict(d.pop("data"))

        hybrid_search_request = cls(
            data=data,
        )

        return hybrid_search_request
