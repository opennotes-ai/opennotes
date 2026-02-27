from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.scoring_status_attributes import ScoringStatusAttributes


T = TypeVar("T", bound="ScoringStatusResource")


@_attrs_define
class ScoringStatusResource:
    """JSON:API resource object for scoring status.

    Attributes:
        attributes (ScoringStatusAttributes): Attributes for scoring status resource.
        type_ (str | Unset):  Default: 'scoring-status'.
        id (str | Unset):  Default: 'current'.
    """

    attributes: ScoringStatusAttributes
    type_: str | Unset = "scoring-status"
    id: str | Unset = "current"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        attributes = self.attributes.to_dict()

        type_ = self.type_

        id = self.id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "attributes": attributes,
            }
        )
        if type_ is not UNSET:
            field_dict["type"] = type_
        if id is not UNSET:
            field_dict["id"] = id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.scoring_status_attributes import ScoringStatusAttributes

        d = dict(src_dict)
        attributes = ScoringStatusAttributes.from_dict(d.pop("attributes"))

        type_ = d.pop("type", UNSET)

        id = d.pop("id", UNSET)

        scoring_status_resource = cls(
            attributes=attributes,
            type_=type_,
            id=id,
        )

        scoring_status_resource.additional_properties = d
        return scoring_status_resource

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
