from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.note_publisher_config_update_data import NotePublisherConfigUpdateData


T = TypeVar("T", bound="NotePublisherConfigUpdateRequest")


@_attrs_define
class NotePublisherConfigUpdateRequest:
    """JSON:API request body for updating a config.

    Attributes:
        data (NotePublisherConfigUpdateData): JSON:API data object for config update.
    """

    data: NotePublisherConfigUpdateData

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
        from ..models.note_publisher_config_update_data import (
            NotePublisherConfigUpdateData,
        )

        d = dict(src_dict)
        data = NotePublisherConfigUpdateData.from_dict(d.pop("data"))

        note_publisher_config_update_request = cls(
            data=data,
        )

        return note_publisher_config_update_request
