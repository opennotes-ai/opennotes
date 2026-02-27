from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="HybridSearchCreateAttributes")


@_attrs_define
class HybridSearchCreateAttributes:
    """Attributes for performing a hybrid search via JSON:API.

    Attributes:
        text (str): Query text to search for (minimum 3 characters). Uses hybrid search combining FTS and semantic
            similarity.
        community_server_id (str): Community server (guild) ID
        limit (int | Unset): Maximum number of results to return Default: 10.
    """

    text: str
    community_server_id: str
    limit: int | Unset = 10

    def to_dict(self) -> dict[str, Any]:
        text = self.text

        community_server_id = self.community_server_id

        limit = self.limit

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "text": text,
                "community_server_id": community_server_id,
            }
        )
        if limit is not UNSET:
            field_dict["limit"] = limit

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        text = d.pop("text")

        community_server_id = d.pop("community_server_id")

        limit = d.pop("limit", UNSET)

        hybrid_search_create_attributes = cls(
            text=text,
            community_server_id=community_server_id,
            limit=limit,
        )

        return hybrid_search_create_attributes
