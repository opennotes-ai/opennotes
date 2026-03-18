from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="CopyRequestsAttributes")


@_attrs_define
class CopyRequestsAttributes:
    """
    Attributes:
        source_community_server_id (UUID): Source community server to copy requests from
    """

    source_community_server_id: UUID

    def to_dict(self) -> dict[str, Any]:
        source_community_server_id = str(self.source_community_server_id)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "source_community_server_id": source_community_server_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source_community_server_id = UUID(d.pop("source_community_server_id"))

        copy_requests_attributes = cls(
            source_community_server_id=source_community_server_id,
        )

        return copy_requests_attributes
