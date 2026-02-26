from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.note_publisher_post_create_data import NotePublisherPostCreateData


T = TypeVar("T", bound="NotePublisherPostCreateRequest")


@_attrs_define
class NotePublisherPostCreateRequest:
    """JSON:API request body for creating a post record.

    Attributes:
        data (NotePublisherPostCreateData): JSON:API data object for post creation.
    """

    data: NotePublisherPostCreateData

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
        from ..models.note_publisher_post_create_data import NotePublisherPostCreateData

        d = dict(src_dict)
        data = NotePublisherPostCreateData.from_dict(d.pop("data"))

        note_publisher_post_create_request = cls(
            data=data,
        )

        return note_publisher_post_create_request
