from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="BatchScoreRequestAttributes")


@_attrs_define
class BatchScoreRequestAttributes:
    """Attributes for batch score request via JSON:API.

    Attributes:
        note_ids (list[UUID]): List of note IDs to retrieve scores for
    """

    note_ids: list[UUID]

    def to_dict(self) -> dict[str, Any]:
        note_ids = []
        for note_ids_item_data in self.note_ids:
            note_ids_item = str(note_ids_item_data)
            note_ids.append(note_ids_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "note_ids": note_ids,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        note_ids = []
        _note_ids = d.pop("note_ids")
        for note_ids_item_data in _note_ids:
            note_ids_item = UUID(note_ids_item_data)

            note_ids.append(note_ids_item)

        batch_score_request_attributes = cls(
            note_ids=note_ids,
        )

        return batch_score_request_attributes
