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

if TYPE_CHECKING:
    from ..models.bulk_scan_create_attributes import BulkScanCreateAttributes


T = TypeVar("T", bound="BulkScanCreateData")


@_attrs_define
class BulkScanCreateData:
    """JSON:API data object for bulk scan creation.

    Attributes:
        type_ (Literal['bulk-scans']): Resource type must be 'bulk-scans'
        attributes (BulkScanCreateAttributes): Attributes for creating a bulk scan.
    """

    type_: Literal["bulk-scans"]
    attributes: BulkScanCreateAttributes

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        attributes = self.attributes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "attributes": attributes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.bulk_scan_create_attributes import BulkScanCreateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["bulk-scans"], d.pop("type"))
        if type_ != "bulk-scans":
            raise ValueError(f"type must match const 'bulk-scans', got '{type_}'")

        attributes = BulkScanCreateAttributes.from_dict(d.pop("attributes"))

        bulk_scan_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return bulk_scan_create_data
