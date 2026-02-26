from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="TokenHoldDetail")


@_attrs_define
class TokenHoldDetail:
    """
    Attributes:
        workflow_id (str):
        weight (int):
        acquired_at (datetime.datetime):
    """

    workflow_id: str
    weight: int
    acquired_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        workflow_id = self.workflow_id

        weight = self.weight

        acquired_at = self.acquired_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "workflow_id": workflow_id,
                "weight": weight,
                "acquired_at": acquired_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        workflow_id = d.pop("workflow_id")

        weight = d.pop("weight")

        acquired_at = isoparse(d.pop("acquired_at"))

        token_hold_detail = cls(
            workflow_id=workflow_id,
            weight=weight,
            acquired_at=acquired_at,
        )

        token_hold_detail.additional_properties = d
        return token_hold_detail

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
