from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SimilaritySearchCreateAttributes")


@_attrs_define
class SimilaritySearchCreateAttributes:
    """Attributes for performing a similarity search via JSON:API.

    Attributes:
        text (str): Message text to search for similar fact-checks
        community_server_id (str): Community server (guild) ID
        dataset_tags (list[str] | Unset): Dataset tags to filter by (e.g., ['snopes', 'politifact'])
        similarity_threshold (float | Unset): Minimum cosine similarity (0.0-1.0) for semantic search pre-filtering
        score_threshold (float | Unset): Minimum CC score (0.0-1.0) for post-fusion filtering Default: 0.1.
        limit (int | Unset): Maximum number of results to return Default: 5.
    """

    text: str
    community_server_id: str
    dataset_tags: list[str] | Unset = UNSET
    similarity_threshold: float | Unset = UNSET
    score_threshold: float | Unset = 0.1
    limit: int | Unset = 5

    def to_dict(self) -> dict[str, Any]:
        text = self.text

        community_server_id = self.community_server_id

        dataset_tags: list[str] | Unset = UNSET
        if not isinstance(self.dataset_tags, Unset):
            dataset_tags = self.dataset_tags

        similarity_threshold = self.similarity_threshold

        score_threshold = self.score_threshold

        limit = self.limit

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "text": text,
                "community_server_id": community_server_id,
            }
        )
        if dataset_tags is not UNSET:
            field_dict["dataset_tags"] = dataset_tags
        if similarity_threshold is not UNSET:
            field_dict["similarity_threshold"] = similarity_threshold
        if score_threshold is not UNSET:
            field_dict["score_threshold"] = score_threshold
        if limit is not UNSET:
            field_dict["limit"] = limit

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        text = d.pop("text")

        community_server_id = d.pop("community_server_id")

        dataset_tags = cast(list[str], d.pop("dataset_tags", UNSET))

        similarity_threshold = d.pop("similarity_threshold", UNSET)

        score_threshold = d.pop("score_threshold", UNSET)

        limit = d.pop("limit", UNSET)

        similarity_search_create_attributes = cls(
            text=text,
            community_server_id=community_server_id,
            dataset_tags=dataset_tags,
            similarity_threshold=similarity_threshold,
            score_threshold=score_threshold,
            limit=limit,
        )

        return similarity_search_create_attributes
