from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="AdminStatusUpdateAttributes")


@_attrs_define
class AdminStatusUpdateAttributes:
    """Attributes for admin status update request.

    Attributes:
        is_opennotes_admin (bool):
    """

    is_opennotes_admin: bool

    def to_dict(self) -> dict[str, Any]:
        is_opennotes_admin = self.is_opennotes_admin

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "is_opennotes_admin": is_opennotes_admin,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        is_opennotes_admin = d.pop("is_opennotes_admin")

        admin_status_update_attributes = cls(
            is_opennotes_admin=is_opennotes_admin,
        )

        return admin_status_update_attributes
