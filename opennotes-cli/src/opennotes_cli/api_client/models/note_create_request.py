from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.note_create_data import NoteCreateData


T = TypeVar("T", bound="NoteCreateRequest")


@_attrs_define
class NoteCreateRequest:
    """JSON:API request body for creating a note.

    Attributes:
        data (NoteCreateData): JSON:API data object for note creation.
    """

    data: NoteCreateData

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
        from ..models.note_create_data import NoteCreateData

        d = dict(src_dict)
        data = NoteCreateData.from_dict(d.pop("data"))

        note_create_request = cls(
            data=data,
        )

        return note_create_request
