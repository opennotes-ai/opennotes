from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="ClaimRelevanceCheckAttributes")


@_attrs_define
class ClaimRelevanceCheckAttributes:
    """Attributes for performing a claim relevance check via JSON:API.

    Attributes:
        original_message (str): The user's original message to check for claims
        matched_content (str): The matched fact-check content
        matched_source (str): URL to the fact-check source
        similarity_score (float): Cosine similarity score of the match
    """

    original_message: str
    matched_content: str
    matched_source: str
    similarity_score: float

    def to_dict(self) -> dict[str, Any]:
        original_message = self.original_message

        matched_content = self.matched_content

        matched_source = self.matched_source

        similarity_score = self.similarity_score

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "original_message": original_message,
                "matched_content": matched_content,
                "matched_source": matched_source,
                "similarity_score": similarity_score,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        original_message = d.pop("original_message")

        matched_content = d.pop("matched_content")

        matched_source = d.pop("matched_source")

        similarity_score = d.pop("similarity_score")

        claim_relevance_check_attributes = cls(
            original_message=original_message,
            matched_content=matched_content,
            matched_source=matched_source,
            similarity_score=similarity_score,
        )

        return claim_relevance_check_attributes
