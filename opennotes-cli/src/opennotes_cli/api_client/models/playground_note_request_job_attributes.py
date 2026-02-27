from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PlaygroundNoteRequestJobAttributes")


@_attrs_define
class PlaygroundNoteRequestJobAttributes:
    """
    Attributes:
        workflow_id (str):
        url_count (int):
        status (str | Unset):  Default: 'ACCEPTED'.
    """

    workflow_id: str
    url_count: int
    status: str | Unset = "ACCEPTED"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        workflow_id = self.workflow_id

        url_count = self.url_count

        status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "workflow_id": workflow_id,
                "url_count": url_count,
            }
        )
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        workflow_id = d.pop("workflow_id")

        url_count = d.pop("url_count")

        status = d.pop("status", UNSET)

        playground_note_request_job_attributes = cls(
            workflow_id=workflow_id,
            url_count=url_count,
            status=status,
        )

        playground_note_request_job_attributes.additional_properties = d
        return playground_note_request_job_attributes

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
