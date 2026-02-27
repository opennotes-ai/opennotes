from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.playground_note_request_data import PlaygroundNoteRequestData


T = TypeVar("T", bound="PlaygroundNoteRequestBody")


@_attrs_define
class PlaygroundNoteRequestBody:
    """
    Attributes:
        data (PlaygroundNoteRequestData):
    """

    data: PlaygroundNoteRequestData

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
        from ..models.playground_note_request_data import PlaygroundNoteRequestData

        d = dict(src_dict)
        data = PlaygroundNoteRequestData.from_dict(d.pop("data"))

        playground_note_request_body = cls(
            data=data,
        )

        return playground_note_request_body
