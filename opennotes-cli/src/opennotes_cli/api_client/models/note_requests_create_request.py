from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.note_requests_create_data import NoteRequestsCreateData


T = TypeVar("T", bound="NoteRequestsCreateRequest")


@_attrs_define
class NoteRequestsCreateRequest:
    """JSON:API request body for creating note requests.

    Attributes:
        data (NoteRequestsCreateData): JSON:API data object for note requests creation.
    """

    data: NoteRequestsCreateData

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
        from ..models.note_requests_create_data import NoteRequestsCreateData

        d = dict(src_dict)
        data = NoteRequestsCreateData.from_dict(d.pop("data"))

        note_requests_create_request = cls(
            data=data,
        )

        return note_requests_create_request
