from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.note_publisher_post_create_attributes import (
        NotePublisherPostCreateAttributes,
    )


T = TypeVar("T", bound="NotePublisherPostCreateData")


@_attrs_define
class NotePublisherPostCreateData:
    """JSON:API data object for post creation.

    Attributes:
        type_ (Literal['note-publisher-posts']): Resource type must be 'note-publisher-posts'
        attributes (NotePublisherPostCreateAttributes): Attributes for creating a note publisher post via JSON:API.
    """

    type_: Literal["note-publisher-posts"]
    attributes: NotePublisherPostCreateAttributes

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        attributes = self.attributes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "attributes": attributes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.note_publisher_post_create_attributes import (
            NotePublisherPostCreateAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["note-publisher-posts"], d.pop("type"))
        if type_ != "note-publisher-posts":
            raise ValueError(
                f"type must match const 'note-publisher-posts', got '{type_}'"
            )

        attributes = NotePublisherPostCreateAttributes.from_dict(d.pop("attributes"))

        note_publisher_post_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return note_publisher_post_create_data
