from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.request_update_data import RequestUpdateData


T = TypeVar("T", bound="RequestUpdateRequest")


@_attrs_define
class RequestUpdateRequest:
    """JSON:API request body for updating a request.

    Attributes:
        data (RequestUpdateData): JSON:API data object for request update.
    """

    data: RequestUpdateData

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
        from ..models.request_update_data import RequestUpdateData

        d = dict(src_dict)
        data = RequestUpdateData.from_dict(d.pop("data"))

        request_update_request = cls(
            data=data,
        )

        return request_update_request
