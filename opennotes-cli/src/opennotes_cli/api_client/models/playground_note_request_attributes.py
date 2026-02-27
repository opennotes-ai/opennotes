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
        urls (list[str] | None | Unset):
        texts (list[str] | None | Unset):
        requested_by (str | Unset):  Default: 'system-playground'.
    """

    urls: list[str] | None | Unset = UNSET
    texts: list[str] | None | Unset = UNSET
    requested_by: str | Unset = "system-playground"

    def to_dict(self) -> dict[str, Any]:
        urls: list[str] | None | Unset
        if isinstance(self.urls, Unset):
            urls = UNSET
        elif isinstance(self.urls, list):
            urls = self.urls

        else:
            urls = self.urls

        texts: list[str] | None | Unset
        if isinstance(self.texts, Unset):
            texts = UNSET
        elif isinstance(self.texts, list):
            texts = self.texts

        else:
            texts = self.texts

        requested_by = self.requested_by

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if urls is not UNSET:
            field_dict["urls"] = urls
        if texts is not UNSET:
            field_dict["texts"] = texts
        if requested_by is not UNSET:
            field_dict["requested_by"] = requested_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_urls(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                urls_type_0 = cast(list[str], data)

                return urls_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        urls = _parse_urls(d.pop("urls", UNSET))

        def _parse_texts(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                texts_type_0 = cast(list[str], data)

                return texts_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        texts = _parse_texts(d.pop("texts", UNSET))

        requested_by = d.pop("requested_by", UNSET)

        playground_note_request_attributes = cls(
            urls=urls,
            texts=texts,
            requested_by=requested_by,
        )

        return playground_note_request_attributes
