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
    from ..models.note_requests_create_attributes import NoteRequestsCreateAttributes


T = TypeVar("T", bound="NoteRequestsCreateData")


@_attrs_define
class NoteRequestsCreateData:
    """JSON:API data object for note requests creation.

    Attributes:
        type_ (Literal['note-requests']): Resource type must be 'note-requests'
        attributes (NoteRequestsCreateAttributes): Attributes for creating note requests from flagged messages.
    """

    type_: Literal["note-requests"]
    attributes: NoteRequestsCreateAttributes

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
        from ..models.note_requests_create_attributes import (
            NoteRequestsCreateAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["note-requests"], d.pop("type"))
        if type_ != "note-requests":
            raise ValueError(f"type must match const 'note-requests', got '{type_}'")

        attributes = NoteRequestsCreateAttributes.from_dict(d.pop("attributes"))

        note_requests_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return note_requests_create_data
