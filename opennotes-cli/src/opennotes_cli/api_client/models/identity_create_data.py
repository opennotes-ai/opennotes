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
    from ..models.identity_create_attributes import IdentityCreateAttributes


T = TypeVar("T", bound="IdentityCreateData")


@_attrs_define
class IdentityCreateData:
    """JSON:API data object for identity create request.

    Attributes:
        attributes (IdentityCreateAttributes): Attributes for identity create request.
        type_ (Literal['identities'] | Unset):  Default: 'identities'.
    """

    attributes: IdentityCreateAttributes
    type_: Literal["identities"] | Unset = "identities"

    def to_dict(self) -> dict[str, Any]:
        attributes = self.attributes.to_dict()

        type_ = self.type_

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "attributes": attributes,
            }
        )
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.identity_create_attributes import IdentityCreateAttributes

        d = dict(src_dict)
        attributes = IdentityCreateAttributes.from_dict(d.pop("attributes"))

        type_ = cast(Literal["identities"] | Unset, d.pop("type", UNSET))
        if type_ != "identities" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'identities', got '{type_}'")

        identity_create_data = cls(
            attributes=attributes,
            type_=type_,
        )

        return identity_create_data
