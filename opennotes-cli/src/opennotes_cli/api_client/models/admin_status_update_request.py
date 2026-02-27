from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.admin_status_update_data import AdminStatusUpdateData


T = TypeVar("T", bound="AdminStatusUpdateRequest")


@_attrs_define
class AdminStatusUpdateRequest:
    """JSON:API request for updating admin status.

    Attributes:
        data (AdminStatusUpdateData): JSON:API data object for admin status update request.
    """

    data: AdminStatusUpdateData

    def to_dict(self) -> dict[str, Any]:
        data = self.data.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "data": data,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.admin_status_update_data import AdminStatusUpdateData

        d = dict(src_dict)
        data = AdminStatusUpdateData.from_dict(d.pop("data"))

        admin_status_update_request = cls(
            data=data,
        )

        return admin_status_update_request
