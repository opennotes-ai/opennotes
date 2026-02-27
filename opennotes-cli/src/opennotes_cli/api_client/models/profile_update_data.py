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

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.profile_update_attributes import ProfileUpdateAttributes


T = TypeVar("T", bound="ProfileUpdateData")


@_attrs_define
class ProfileUpdateData:
    """JSON:API data object for profile update request.

    Attributes:
        id (str):
        attributes (ProfileUpdateAttributes): Attributes for profile update request.
        type_ (Literal['profiles'] | Unset):  Default: 'profiles'.
    """

    id: str
    attributes: ProfileUpdateAttributes
    type_: Literal["profiles"] | Unset = "profiles"

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        attributes = self.attributes.to_dict()

        type_ = self.type_

        field_dict: dict[str, Any] = {}

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
        from ..models.profile_update_attributes import ProfileUpdateAttributes

        d = dict(src_dict)
        id = d.pop("id")

        attributes = ProfileUpdateAttributes.from_dict(d.pop("attributes"))

        type_ = cast(Literal["profiles"] | Unset, d.pop("type", UNSET))
        if type_ != "profiles" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'profiles', got '{type_}'")

        profile_update_data = cls(
            id=id,
            attributes=attributes,
            type_=type_,
        )

        return profile_update_data
