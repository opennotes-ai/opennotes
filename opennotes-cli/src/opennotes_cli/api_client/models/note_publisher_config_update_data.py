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
    from ..models.note_publisher_config_update_attributes import (
        NotePublisherConfigUpdateAttributes,
    )


T = TypeVar("T", bound="NotePublisherConfigUpdateData")


@_attrs_define
class NotePublisherConfigUpdateData:
    """JSON:API data object for config update.

    Attributes:
        type_ (Literal['note-publisher-configs']): Resource type must be 'note-publisher-configs'
        id (str): Config ID
        attributes (NotePublisherConfigUpdateAttributes): Attributes for updating a note publisher config via JSON:API.
    """

    type_: Literal["note-publisher-configs"]
    id: str
    attributes: NotePublisherConfigUpdateAttributes

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        id = self.id

        attributes = self.attributes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "id": id,
                "attributes": attributes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.note_publisher_config_update_attributes import (
            NotePublisherConfigUpdateAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["note-publisher-configs"], d.pop("type"))
        if type_ != "note-publisher-configs":
            raise ValueError(
                f"type must match const 'note-publisher-configs', got '{type_}'"
            )

        id = d.pop("id")

        attributes = NotePublisherConfigUpdateAttributes.from_dict(d.pop("attributes"))

        note_publisher_config_update_data = cls(
            type_=type_,
            id=id,
            attributes=attributes,
        )

        return note_publisher_config_update_data
