from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.flagged_message_resource import FlaggedMessageResource
    from ..models.jsonapi_links import JSONAPILinks
    from ..models.latest_scan_jsonapi_response_jsonapi import (
        LatestScanJSONAPIResponseJsonapi,
    )
    from ..models.latest_scan_resource import LatestScanResource


T = TypeVar("T", bound="LatestScanJSONAPIResponse")


@_attrs_define
class LatestScanJSONAPIResponse:
    """JSON:API response for the latest scan with included flagged messages.

    Attributes:
        data (LatestScanResource): JSON:API resource object for the latest scan.
        included (list[FlaggedMessageResource] | Unset):
        jsonapi (LatestScanJSONAPIResponseJsonapi | Unset):
        links (JSONAPILinks | None | Unset):
    """

    data: LatestScanResource
    included: list[FlaggedMessageResource] | Unset = UNSET
    jsonapi: LatestScanJSONAPIResponseJsonapi | Unset = UNSET
    links: JSONAPILinks | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.jsonapi_links import JSONAPILinks

        data = self.data.to_dict()

        included: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.included, Unset):
            included = []
            for included_item_data in self.included:
                included_item = included_item_data.to_dict()
                included.append(included_item)

        jsonapi: dict[str, Any] | Unset = UNSET
        if not isinstance(self.jsonapi, Unset):
            jsonapi = self.jsonapi.to_dict()

        links: dict[str, Any] | None | Unset
        if isinstance(self.links, Unset):
            links = UNSET
        elif isinstance(self.links, JSONAPILinks):
            links = self.links.to_dict()
        else:
            links = self.links

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data": data,
            }
        )
        if included is not UNSET:
            field_dict["included"] = included
        if jsonapi is not UNSET:
            field_dict["jsonapi"] = jsonapi
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.flagged_message_resource import FlaggedMessageResource
        from ..models.jsonapi_links import JSONAPILinks
        from ..models.latest_scan_jsonapi_response_jsonapi import (
            LatestScanJSONAPIResponseJsonapi,
        )
        from ..models.latest_scan_resource import LatestScanResource

        d = dict(src_dict)
        data = LatestScanResource.from_dict(d.pop("data"))

        _included = d.pop("included", UNSET)
        included: list[FlaggedMessageResource] | Unset = UNSET
        if _included is not UNSET:
            included = []
            for included_item_data in _included:
                included_item = FlaggedMessageResource.from_dict(included_item_data)

                included.append(included_item)

        _jsonapi = d.pop("jsonapi", UNSET)
        jsonapi: LatestScanJSONAPIResponseJsonapi | Unset
        if isinstance(_jsonapi, Unset):
            jsonapi = UNSET
        else:
            jsonapi = LatestScanJSONAPIResponseJsonapi.from_dict(_jsonapi)

        def _parse_links(data: object) -> JSONAPILinks | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                links_type_0 = JSONAPILinks.from_dict(data)

                return links_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(JSONAPILinks | None | Unset, data)

        links = _parse_links(d.pop("links", UNSET))

        latest_scan_jsonapi_response = cls(
            data=data,
            included=included,
            jsonapi=jsonapi,
            links=links,
        )

        latest_scan_jsonapi_response.additional_properties = d
        return latest_scan_jsonapi_response

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
