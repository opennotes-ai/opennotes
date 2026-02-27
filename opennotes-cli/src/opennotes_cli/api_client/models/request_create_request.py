from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.request_create_data import RequestCreateData


T = TypeVar("T", bound="RequestCreateRequest")


@_attrs_define
class RequestCreateRequest:
    """JSON:API request body for creating a request.

    Attributes:
        data (RequestCreateData): JSON:API data object for request creation.
    """

    data: RequestCreateData

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
        from ..models.request_create_data import RequestCreateData

        d = dict(src_dict)
        data = RequestCreateData.from_dict(d.pop("data"))

        request_create_request = cls(
            data=data,
        )

        return request_create_request
