from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.jsonapi_links import JSONAPILinks
    from ..models.note_stats_resource import NoteStatsResource
    from ..models.note_stats_single_response_jsonapi import (
        NoteStatsSingleResponseJsonapi,
    )


T = TypeVar("T", bound="NoteStatsSingleResponse")


@_attrs_define
class NoteStatsSingleResponse:
    """JSON:API response for note statistics.

    Attributes:
        data (NoteStatsResource): JSON:API resource object for note statistics.
        jsonapi (NoteStatsSingleResponseJsonapi | Unset):
        links (JSONAPILinks | None | Unset):
    """

    data: NoteStatsResource
    jsonapi: NoteStatsSingleResponseJsonapi | Unset = UNSET
    links: JSONAPILinks | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.jsonapi_links import JSONAPILinks

        data = self.data.to_dict()

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
        if jsonapi is not UNSET:
            field_dict["jsonapi"] = jsonapi
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.jsonapi_links import JSONAPILinks
        from ..models.note_stats_resource import NoteStatsResource
        from ..models.note_stats_single_response_jsonapi import (
            NoteStatsSingleResponseJsonapi,
        )

        d = dict(src_dict)
        data = NoteStatsResource.from_dict(d.pop("data"))

        _jsonapi = d.pop("jsonapi", UNSET)
        jsonapi: NoteStatsSingleResponseJsonapi | Unset
        if isinstance(_jsonapi, Unset):
            jsonapi = UNSET
        else:
            jsonapi = NoteStatsSingleResponseJsonapi.from_dict(_jsonapi)

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

        note_stats_single_response = cls(
            data=data,
            jsonapi=jsonapi,
            links=links,
        )

        note_stats_single_response.additional_properties = d
        return note_stats_single_response

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
