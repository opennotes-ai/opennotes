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

if TYPE_CHECKING:
    from ..models.claim_relevance_check_attributes import ClaimRelevanceCheckAttributes


T = TypeVar("T", bound="ClaimRelevanceCheckCreateData")


@_attrs_define
class ClaimRelevanceCheckCreateData:
    """JSON:API data object for claim relevance check.

    Attributes:
        type_ (Literal['claim-relevance-checks']): Resource type must be 'claim-relevance-checks'
        attributes (ClaimRelevanceCheckAttributes): Attributes for performing a claim relevance check via JSON:API.
    """

    type_: Literal["claim-relevance-checks"]
    attributes: ClaimRelevanceCheckAttributes
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        attributes = self.attributes.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "attributes": attributes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.claim_relevance_check_attributes import (
            ClaimRelevanceCheckAttributes,
        )

        d = dict(src_dict)
        type_ = cast(Literal["claim-relevance-checks"], d.pop("type"))
        if type_ != "claim-relevance-checks":
            raise ValueError(
                f"type must match const 'claim-relevance-checks', got '{type_}'"
            )

        attributes = ClaimRelevanceCheckAttributes.from_dict(d.pop("attributes"))

        claim_relevance_check_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        claim_relevance_check_create_data.additional_properties = d
        return claim_relevance_check_create_data

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
