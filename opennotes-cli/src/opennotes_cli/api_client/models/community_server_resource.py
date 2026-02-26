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
    from ..models.community_server_attributes import CommunityServerAttributes


T = TypeVar("T", bound="CommunityServerResource")


@_attrs_define
class CommunityServerResource:
    """JSON:API resource object for a community server.

    Attributes:
        id (str):
        attributes (CommunityServerAttributes): Community server attributes for JSON:API resource.
        type_ (Literal['community-servers'] | Unset):  Default: 'community-servers'.
    """

    id: str
    attributes: CommunityServerAttributes
    type_: Literal["community-servers"] | Unset = "community-servers"
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
        from ..models.community_server_attributes import CommunityServerAttributes

        d = dict(src_dict)
        id = d.pop("id")

        attributes = CommunityServerAttributes.from_dict(d.pop("attributes"))

        type_ = cast(Literal["community-servers"] | Unset, d.pop("type", UNSET))
        if type_ != "community-servers" and not isinstance(type_, Unset):
            raise ValueError(
                f"type must match const 'community-servers', got '{type_}'"
            )

        community_server_resource = cls(
            id=id,
            attributes=attributes,
            type_=type_,
        )

        community_server_resource.additional_properties = d
        return community_server_resource

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
