from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.fact_check_match_resource import FactCheckMatchResource


T = TypeVar("T", bound="SimilaritySearchResultAttributes")


@_attrs_define
class SimilaritySearchResultAttributes:
    """Attributes for similarity search result.

    Attributes:
        matches (list[FactCheckMatchResource]): Matching fact-check items
        query_text (str): Original query text
        dataset_tags (list[str]): Dataset tags used for filtering
        similarity_threshold (float): Cosine similarity threshold applied
        score_threshold (float): CC score threshold applied
        total_matches (int): Number of matches found
    """

    matches: list[FactCheckMatchResource]
    query_text: str
    dataset_tags: list[str]
    similarity_threshold: float
    score_threshold: float
    total_matches: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        matches = []
        for matches_item_data in self.matches:
            matches_item = matches_item_data.to_dict()
            matches.append(matches_item)

        query_text = self.query_text

        dataset_tags = self.dataset_tags

        similarity_threshold = self.similarity_threshold

        score_threshold = self.score_threshold

        total_matches = self.total_matches

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "matches": matches,
                "query_text": query_text,
                "dataset_tags": dataset_tags,
                "similarity_threshold": similarity_threshold,
                "score_threshold": score_threshold,
                "total_matches": total_matches,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.fact_check_match_resource import FactCheckMatchResource

        d = dict(src_dict)
        matches = []
        _matches = d.pop("matches")
        for matches_item_data in _matches:
            matches_item = FactCheckMatchResource.from_dict(matches_item_data)

            matches.append(matches_item)

        query_text = d.pop("query_text")

        dataset_tags = cast(list[str], d.pop("dataset_tags"))

        similarity_threshold = d.pop("similarity_threshold")

        score_threshold = d.pop("score_threshold")

        total_matches = d.pop("total_matches")

        similarity_search_result_attributes = cls(
            matches=matches,
            query_text=query_text,
            dataset_tags=dataset_tags,
            similarity_threshold=similarity_threshold,
            score_threshold=score_threshold,
            total_matches=total_matches,
        )

        similarity_search_result_attributes.additional_properties = d
        return similarity_search_result_attributes

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
