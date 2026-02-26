from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PlaygroundNoteRequestAttributes")


@_attrs_define
class PlaygroundNoteRequestAttributes:
    """
    Attributes:
        urls (list[str]):
        requested_by (str | Unset):  Default: 'system-playground'.
    """

    urls: list[str]
    requested_by: str | Unset = "system-playground"

    def to_dict(self) -> dict[str, Any]:
        urls = self.urls

        requested_by = self.requested_by

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "urls": urls,
            }
        )
        if requested_by is not UNSET:
            field_dict["requested_by"] = requested_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        urls = cast(list[str], d.pop("urls"))

        requested_by = d.pop("requested_by", UNSET)

        playground_note_request_attributes = cls(
            urls=urls,
            requested_by=requested_by,
        )

        return playground_note_request_attributes
