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
    from ..models.note_create_attributes import NoteCreateAttributes


T = TypeVar("T", bound="NoteCreateData")


@_attrs_define
class NoteCreateData:
    """JSON:API data object for note creation.

    Attributes:
        type_ (Literal['notes']): Resource type must be 'notes'
        attributes (NoteCreateAttributes): Attributes for creating a note via JSON:API.
    """

    type_: Literal["notes"]
    attributes: NoteCreateAttributes

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
        from ..models.note_create_attributes import NoteCreateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["notes"], d.pop("type"))
        if type_ != "notes":
            raise ValueError(f"type must match const 'notes', got '{type_}'")

        attributes = NoteCreateAttributes.from_dict(d.pop("attributes"))

        note_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return note_create_data
