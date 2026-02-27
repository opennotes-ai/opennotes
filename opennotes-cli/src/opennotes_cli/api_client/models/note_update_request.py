from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.note_update_data import NoteUpdateData


T = TypeVar("T", bound="NoteUpdateRequest")


@_attrs_define
class NoteUpdateRequest:
    """JSON:API request body for updating a note.

    Attributes:
        data (NoteUpdateData): JSON:API data object for note update.
    """

    data: NoteUpdateData

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
        from ..models.note_update_data import NoteUpdateData

        d = dict(src_dict)
        data = NoteUpdateData.from_dict(d.pop("data"))

        note_update_request = cls(
            data=data,
        )

        return note_update_request
