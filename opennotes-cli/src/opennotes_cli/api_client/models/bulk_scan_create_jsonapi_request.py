from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.bulk_scan_create_data import BulkScanCreateData


T = TypeVar("T", bound="BulkScanCreateJSONAPIRequest")


@_attrs_define
class BulkScanCreateJSONAPIRequest:
    """JSON:API request body for creating a bulk scan.

    Attributes:
        data (BulkScanCreateData): JSON:API data object for bulk scan creation.
    """

    data: BulkScanCreateData

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
        from ..models.bulk_scan_create_data import BulkScanCreateData

        d = dict(src_dict)
        data = BulkScanCreateData.from_dict(d.pop("data"))

        bulk_scan_create_jsonapi_request = cls(
            data=data,
        )

        return bulk_scan_create_jsonapi_request
