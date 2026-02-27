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
    from ..models.admin_status_update_attributes import AdminStatusUpdateAttributes


T = TypeVar("T", bound="AdminStatusUpdateData")


@_attrs_define
class AdminStatusUpdateData:
    """JSON:API data object for admin status update request.

    Attributes:
        id (str):
        attributes (AdminStatusUpdateAttributes): Attributes for admin status update request.
        type_ (Literal['admin-status'] | Unset):  Default: 'admin-status'.
    """

    id: str
    attributes: AdminStatusUpdateAttributes
    type_: Literal["admin-status"] | Unset = "admin-status"

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
        from ..models.admin_status_update_attributes import AdminStatusUpdateAttributes

        d = dict(src_dict)
        id = d.pop("id")

        attributes = AdminStatusUpdateAttributes.from_dict(d.pop("attributes"))

        type_ = cast(Literal["admin-status"] | Unset, d.pop("type", UNSET))
        if type_ != "admin-status" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'admin-status', got '{type_}'")

        admin_status_update_data = cls(
            id=id,
            attributes=attributes,
            type_=type_,
        )

        return admin_status_update_data
