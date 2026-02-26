from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="ExplanationCreateAttributes")


@_attrs_define
class ExplanationCreateAttributes:
    """Attributes for generating a scan explanation.

    Attributes:
        original_message (str): Original message content that was flagged
        fact_check_item_id (UUID): UUID of the matched FactCheckItem
        community_server_id (UUID): Community server UUID for context
    """

    original_message: str
    fact_check_item_id: UUID
    community_server_id: UUID

    def to_dict(self) -> dict[str, Any]:
        original_message = self.original_message

        fact_check_item_id = str(self.fact_check_item_id)

        community_server_id = str(self.community_server_id)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "original_message": original_message,
                "fact_check_item_id": fact_check_item_id,
                "community_server_id": community_server_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        original_message = d.pop("original_message")

        fact_check_item_id = UUID(d.pop("fact_check_item_id"))

        community_server_id = UUID(d.pop("community_server_id"))

        explanation_create_attributes = cls(
            original_message=original_message,
            fact_check_item_id=fact_check_item_id,
            community_server_id=community_server_id,
        )

        return explanation_create_attributes
