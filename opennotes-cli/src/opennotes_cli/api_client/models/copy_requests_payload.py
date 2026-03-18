from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.copy_requests_data import CopyRequestsData


T = TypeVar("T", bound="CopyRequestsPayload")


@_attrs_define
class CopyRequestsPayload:
    """
    Attributes:
        data (CopyRequestsData):
    """

    data: CopyRequestsData

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
        from ..models.copy_requests_data import CopyRequestsData

        d = dict(src_dict)
        data = CopyRequestsData.from_dict(d.pop("data"))

        copy_requests_payload = cls(
            data=data,
        )

        return copy_requests_payload
