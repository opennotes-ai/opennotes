from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="NoteRequestsCreateAttributes")


@_attrs_define
class NoteRequestsCreateAttributes:
    """Attributes for creating note requests from flagged messages.

    Attributes:
        message_ids (list[str]): List of message IDs to create note requests for
        generate_ai_notes (bool | Unset): Whether to generate AI draft notes Default: False.
    """

    message_ids: list[str]
    generate_ai_notes: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        message_ids = self.message_ids

        generate_ai_notes = self.generate_ai_notes

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "message_ids": message_ids,
            }
        )
        if generate_ai_notes is not UNSET:
            field_dict["generate_ai_notes"] = generate_ai_notes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message_ids = cast(list[str], d.pop("message_ids"))

        generate_ai_notes = d.pop("generate_ai_notes", UNSET)

        note_requests_create_attributes = cls(
            message_ids=message_ids,
            generate_ai_notes=generate_ai_notes,
        )

        return note_requests_create_attributes
