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
    from ..models.admin_status_attributes import AdminStatusAttributes


T = TypeVar("T", bound="AdminStatusResource")


@_attrs_define
class AdminStatusResource:
    """JSON:API resource object for admin status.

    Attributes:
        id (str):
        attributes (AdminStatusAttributes): Admin status attributes for JSON:API resource.
        type_ (Literal['admin-status'] | Unset):  Default: 'admin-status'.
    """

    id: str
    attributes: AdminStatusAttributes
    type_: Literal["admin-status"] | Unset = "admin-status"
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
        from ..models.admin_status_attributes import AdminStatusAttributes

        d = dict(src_dict)
        id = d.pop("id")

        attributes = AdminStatusAttributes.from_dict(d.pop("attributes"))

        type_ = cast(Literal["admin-status"] | Unset, d.pop("type", UNSET))
        if type_ != "admin-status" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'admin-status', got '{type_}'")

        admin_status_resource = cls(
            id=id,
            attributes=attributes,
            type_=type_,
        )

        admin_status_resource.additional_properties = d
        return admin_status_resource

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
