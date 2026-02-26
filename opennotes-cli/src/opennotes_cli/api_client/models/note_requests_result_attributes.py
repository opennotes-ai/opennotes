from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NoteRequestsResultAttributes")


@_attrs_define
class NoteRequestsResultAttributes:
    """Attributes for note requests creation result.

    Attributes:
        created_count (int): Number of note requests created
        request_ids (list[str] | Unset): Created request IDs
    """

    created_count: int
    request_ids: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created_count = self.created_count

        request_ids: list[str] | Unset = UNSET
        if not isinstance(self.request_ids, Unset):
            request_ids = self.request_ids

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "created_count": created_count,
            }
        )
        if request_ids is not UNSET:
            field_dict["request_ids"] = request_ids

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_count = d.pop("created_count")

        request_ids = cast(list[str], d.pop("request_ids", UNSET))

        note_requests_result_attributes = cls(
            created_count=created_count,
            request_ids=request_ids,
        )

        note_requests_result_attributes.additional_properties = d
        return note_requests_result_attributes

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
