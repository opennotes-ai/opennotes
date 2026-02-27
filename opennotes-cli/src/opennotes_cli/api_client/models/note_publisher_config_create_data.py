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
    from ..models.note_publisher_config_create_attributes import (
        NotePublisherConfigCreateAttributes,
    )


T = TypeVar("T", bound="NotePublisherConfigCreateData")


@_attrs_define
class NotePublisherConfigCreateData:
    """JSON:API data object for config creation.

    Attributes:
        type_ (Literal['note-publisher-configs']): Resource type must be 'note-publisher-configs'
        attributes (NotePublisherConfigCreateAttributes): Attributes for creating a note publisher config via JSON:API.
    """

    type_: Literal["note-publisher-configs"]
    attributes: NotePublisherConfigCreateAttributes

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
        from ..models.note_publisher_config_create_attributes import (
            NotePublisherConfigCreateAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["note-publisher-configs"], d.pop("type"))
        if type_ != "note-publisher-configs":
            raise ValueError(
                f"type must match const 'note-publisher-configs', got '{type_}'"
            )

        attributes = NotePublisherConfigCreateAttributes.from_dict(d.pop("attributes"))

        note_publisher_config_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return note_publisher_config_create_data
