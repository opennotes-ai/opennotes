from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.candidate_attributes import CandidateAttributes


T = TypeVar("T", bound="CandidateResource")


@_attrs_define
class CandidateResource:
    """JSON:API resource object for a fact-check candidate.

    Attributes:
        id (str):
        attributes (CandidateAttributes): JSON:API attributes for a fact-check candidate.
        type_ (Literal['fact-check-candidates'] | Unset):  Default: 'fact-check-candidates'.
    """

    id: str
    attributes: CandidateAttributes
    type_: Literal["fact-check-candidates"] | Unset = "fact-check-candidates"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        attributes = self.attributes.to_dict()

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "attributes": attributes,
            }
        )
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.candidate_attributes import CandidateAttributes

        d = dict(src_dict)
        id = d.pop("id")

        attributes = CandidateAttributes.from_dict(d.pop("attributes"))

        type_ = cast(Literal["fact-check-candidates"] | Unset, d.pop("type", UNSET))
        if type_ != "fact-check-candidates" and not isinstance(type_, Unset):
            raise ValueError(
                f"type must match const 'fact-check-candidates', got '{type_}'"
            )

        candidate_resource = cls(
            id=id,
            attributes=attributes,
            type_=type_,
        )

        candidate_resource.additional_properties = d
        return candidate_resource

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
