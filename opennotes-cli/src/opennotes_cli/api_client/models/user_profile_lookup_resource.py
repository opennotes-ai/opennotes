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
    from ..models.user_profile_lookup_attributes import UserProfileLookupAttributes


T = TypeVar("T", bound="UserProfileLookupResource")


@_attrs_define
class UserProfileLookupResource:
    """JSON:API resource object for user profile lookup response.

    Attributes:
        id (str):
        attributes (UserProfileLookupAttributes): Attributes for user profile lookup response.
        type_ (Literal['user-profiles'] | Unset):  Default: 'user-profiles'.
    """

    id: str
    attributes: UserProfileLookupAttributes
    type_: Literal["user-profiles"] | Unset = "user-profiles"
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
        from ..models.user_profile_lookup_attributes import UserProfileLookupAttributes

        d = dict(src_dict)
        id = d.pop("id")

        attributes = UserProfileLookupAttributes.from_dict(d.pop("attributes"))

        type_ = cast(Literal["user-profiles"] | Unset, d.pop("type", UNSET))
        if type_ != "user-profiles" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'user-profiles', got '{type_}'")

        user_profile_lookup_resource = cls(
            id=id,
            attributes=attributes,
            type_=type_,
        )

        user_profile_lookup_resource.additional_properties = d
        return user_profile_lookup_resource

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
