from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.source_kind import SourceKind

T = TypeVar("T", bound="SupportingFact")


@_attrs_define
class SupportingFact:
    """A single supporting statement for a deduped claim.

    Attributes:
        statement (str):
        source_kind (SourceKind): Origin of a supporting fact used by the evidence slot.
        source_ref (str):
    """

    statement: str
    source_kind: SourceKind
    source_ref: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        statement = self.statement

        source_kind = self.source_kind.value

        source_ref = self.source_ref

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "statement": statement,
                "source_kind": source_kind,
                "source_ref": source_ref,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        statement = d.pop("statement")

        source_kind = SourceKind(d.pop("source_kind"))

        source_ref = d.pop("source_ref")

        supporting_fact = cls(
            statement=statement,
            source_kind=source_kind,
            source_ref=source_ref,
        )

        supporting_fact.additional_properties = d
        return supporting_fact

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
