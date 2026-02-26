from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.hybrid_search_match_resource import HybridSearchMatchResource


T = TypeVar("T", bound="HybridSearchResultAttributes")


@_attrs_define
class HybridSearchResultAttributes:
    """Attributes for hybrid search result.

    Attributes:
        matches (list[HybridSearchMatchResource]): Matching fact-check items ranked by CC score
        query_text (str): Original query text
        total_matches (int): Number of matches found
    """

    matches: list[HybridSearchMatchResource]
    query_text: str
    total_matches: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        matches = []
        for matches_item_data in self.matches:
            matches_item = matches_item_data.to_dict()
            matches.append(matches_item)

        query_text = self.query_text

        total_matches = self.total_matches

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "matches": matches,
                "query_text": query_text,
                "total_matches": total_matches,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.hybrid_search_match_resource import HybridSearchMatchResource

        d = dict(src_dict)
        matches = []
        _matches = d.pop("matches")
        for matches_item_data in _matches:
            matches_item = HybridSearchMatchResource.from_dict(matches_item_data)

            matches.append(matches_item)

        query_text = d.pop("query_text")

        total_matches = d.pop("total_matches")

        hybrid_search_result_attributes = cls(
            matches=matches,
            query_text=query_text,
            total_matches=total_matches,
        )

        hybrid_search_result_attributes.additional_properties = d
        return hybrid_search_result_attributes

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
