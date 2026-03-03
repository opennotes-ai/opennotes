from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DetailedRequestData")


@_attrs_define
class DetailedRequestData:
    """
    Attributes:
        request_id (str):
        content (None | str | Unset):
        content_type (None | str | Unset):
        note_count (int | Unset):  Default: 0.
        variance_score (float | Unset):  Default: 0.0.
    """

    request_id: str
    content: None | str | Unset = UNSET
    content_type: None | str | Unset = UNSET
    note_count: int | Unset = 0
    variance_score: float | Unset = 0.0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        request_id = self.request_id

        content: None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        else:
            content = self.content

        content_type: None | str | Unset
        if isinstance(self.content_type, Unset):
            content_type = UNSET
        else:
            content_type = self.content_type

        note_count = self.note_count

        variance_score = self.variance_score

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "request_id": request_id,
            }
        )
        if content is not UNSET:
            field_dict["content"] = content
        if content_type is not UNSET:
            field_dict["content_type"] = content_type
        if note_count is not UNSET:
            field_dict["note_count"] = note_count
        if variance_score is not UNSET:
            field_dict["variance_score"] = variance_score

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        request_id = d.pop("request_id")

        def _parse_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))

        def _parse_content_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content_type = _parse_content_type(d.pop("content_type", UNSET))

        note_count = d.pop("note_count", UNSET)

        variance_score = d.pop("variance_score", UNSET)

        detailed_request_data = cls(
            request_id=request_id,
            content=content,
            content_type=content_type,
            note_count=note_count,
            variance_score=variance_score,
        )

        detailed_request_data.additional_properties = d
        return detailed_request_data

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
