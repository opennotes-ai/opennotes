from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.headline_summary_kind import HeadlineSummaryKind
from ..types import UNSET, Unset

T = TypeVar("T", bound="HeadlineSummary")


@_attrs_define
class HeadlineSummary:
    """
    Attributes:
        text (str):
        kind (HeadlineSummaryKind):
        unavailable_inputs (list[str] | Unset):
    """

    text: str
    kind: HeadlineSummaryKind
    unavailable_inputs: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        text = self.text

        kind = self.kind.value

        unavailable_inputs: list[str] | Unset = UNSET
        if not isinstance(self.unavailable_inputs, Unset):
            unavailable_inputs = self.unavailable_inputs

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "text": text,
                "kind": kind,
            }
        )
        if unavailable_inputs is not UNSET:
            field_dict["unavailable_inputs"] = unavailable_inputs

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        text = d.pop("text")

        kind = HeadlineSummaryKind(d.pop("kind"))

        unavailable_inputs = cast(list[str], d.pop("unavailable_inputs", UNSET))

        headline_summary = cls(
            text=text,
            kind=kind,
            unavailable_inputs=unavailable_inputs,
        )

        headline_summary.additional_properties = d
        return headline_summary

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
