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
    from ..models.playground_note_request_attributes import (
        PlaygroundNoteRequestAttributes,
    )


T = TypeVar("T", bound="PlaygroundNoteRequestData")


@_attrs_define
class PlaygroundNoteRequestData:
    """
    Attributes:
        type_ (Literal['playground-note-requests']):
        attributes (PlaygroundNoteRequestAttributes):
    """

    type_: Literal["playground-note-requests"]
    attributes: PlaygroundNoteRequestAttributes

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
        from ..models.playground_note_request_attributes import (
            PlaygroundNoteRequestAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["playground-note-requests"], d.pop("type"))
        if type_ != "playground-note-requests":
            raise ValueError(
                f"type must match const 'playground-note-requests', got '{type_}'"
            )

        attributes = PlaygroundNoteRequestAttributes.from_dict(d.pop("attributes"))

        playground_note_request_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return playground_note_request_data
