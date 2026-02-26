from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.latest_scan_attributes import LatestScanAttributes
    from ..models.latest_scan_resource_relationships_type_0 import (
        LatestScanResourceRelationshipsType0,
    )


T = TypeVar("T", bound="LatestScanResource")


@_attrs_define
class LatestScanResource:
    """JSON:API resource object for the latest scan.

    Attributes:
        id (str):
        attributes (LatestScanAttributes): Attributes for the latest scan resource.
        type_ (str | Unset):  Default: 'bulk-scans'.
        relationships (LatestScanResourceRelationshipsType0 | None | Unset):
    """

    id: str
    attributes: LatestScanAttributes
    type_: str | Unset = "bulk-scans"
    relationships: LatestScanResourceRelationshipsType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.latest_scan_resource_relationships_type_0 import (
            LatestScanResourceRelationshipsType0,
        )

        id = self.id

        attributes = self.attributes.to_dict()

        type_ = self.type_

        relationships: dict[str, Any] | None | Unset
        if isinstance(self.relationships, Unset):
            relationships = UNSET
        elif isinstance(self.relationships, LatestScanResourceRelationshipsType0):
            relationships = self.relationships.to_dict()
        else:
            relationships = self.relationships

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
        if relationships is not UNSET:
            field_dict["relationships"] = relationships

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.latest_scan_attributes import LatestScanAttributes
        from ..models.latest_scan_resource_relationships_type_0 import (
            LatestScanResourceRelationshipsType0,
        )

        d = dict(src_dict)
        id = d.pop("id")

        attributes = LatestScanAttributes.from_dict(d.pop("attributes"))

        type_ = d.pop("type", UNSET)

        def _parse_relationships(
            data: object,
        ) -> LatestScanResourceRelationshipsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                relationships_type_0 = LatestScanResourceRelationshipsType0.from_dict(
                    data
                )

                return relationships_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LatestScanResourceRelationshipsType0 | None | Unset, data)

        relationships = _parse_relationships(d.pop("relationships", UNSET))

        latest_scan_resource = cls(
            id=id,
            attributes=attributes,
            type_=type_,
            relationships=relationships,
        )

        latest_scan_resource.additional_properties = d
        return latest_scan_resource

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
