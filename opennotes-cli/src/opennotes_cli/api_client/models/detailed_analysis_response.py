from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.detailed_analysis_response_jsonapi import (
        DetailedAnalysisResponseJsonapi,
    )
    from ..models.detailed_analysis_response_meta_type_0 import (
        DetailedAnalysisResponseMetaType0,
    )
    from ..models.detailed_note_resource import DetailedNoteResource
    from ..models.jsonapi_links import JSONAPILinks


T = TypeVar("T", bound="DetailedAnalysisResponse")


@_attrs_define
class DetailedAnalysisResponse:
    """
    Attributes:
        data (list[DetailedNoteResource]):
        jsonapi (DetailedAnalysisResponseJsonapi | Unset):
        links (JSONAPILinks | None | Unset):
        meta (DetailedAnalysisResponseMetaType0 | None | Unset):
    """

    data: list[DetailedNoteResource]
    jsonapi: DetailedAnalysisResponseJsonapi | Unset = UNSET
    links: JSONAPILinks | None | Unset = UNSET
    meta: DetailedAnalysisResponseMetaType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.detailed_analysis_response_meta_type_0 import (
            DetailedAnalysisResponseMetaType0,
        )
        from ..models.jsonapi_links import JSONAPILinks

        data = []
        for data_item_data in self.data:
            data_item = data_item_data.to_dict()
            data.append(data_item)

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

        meta: dict[str, Any] | None | Unset
        if isinstance(self.meta, Unset):
            meta = UNSET
        elif isinstance(self.meta, DetailedAnalysisResponseMetaType0):
            meta = self.meta.to_dict()
        else:
            meta = self.meta

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
        if meta is not UNSET:
            field_dict["meta"] = meta

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.detailed_analysis_response_jsonapi import (
            DetailedAnalysisResponseJsonapi,
        )
        from ..models.detailed_analysis_response_meta_type_0 import (
            DetailedAnalysisResponseMetaType0,
        )
        from ..models.detailed_note_resource import DetailedNoteResource
        from ..models.jsonapi_links import JSONAPILinks

        d = dict(src_dict)
        data = []
        _data = d.pop("data")
        for data_item_data in _data:
            data_item = DetailedNoteResource.from_dict(data_item_data)

            data.append(data_item)

        _jsonapi = d.pop("jsonapi", UNSET)
        jsonapi: DetailedAnalysisResponseJsonapi | Unset
        if isinstance(_jsonapi, Unset):
            jsonapi = UNSET
        else:
            jsonapi = DetailedAnalysisResponseJsonapi.from_dict(_jsonapi)

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

        def _parse_meta(
            data: object,
        ) -> DetailedAnalysisResponseMetaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                meta_type_0 = DetailedAnalysisResponseMetaType0.from_dict(data)

                return meta_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DetailedAnalysisResponseMetaType0 | None | Unset, data)

        meta = _parse_meta(d.pop("meta", UNSET))

        detailed_analysis_response = cls(
            data=data,
            jsonapi=jsonapi,
            links=links,
            meta=meta,
        )

        detailed_analysis_response.additional_properties = d
        return detailed_analysis_response

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
