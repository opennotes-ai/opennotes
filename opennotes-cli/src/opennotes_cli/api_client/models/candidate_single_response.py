from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.candidate_resource import CandidateResource
    from ..models.candidate_single_response_jsonapi import (
        CandidateSingleResponseJsonapi,
    )
    from ..models.jsonapi_links import JSONAPILinks


T = TypeVar("T", bound="CandidateSingleResponse")


@_attrs_define
class CandidateSingleResponse:
    """JSON:API response for a single candidate.

    Attributes:
        data (CandidateResource): JSON:API resource object for a fact-check candidate.
        jsonapi (CandidateSingleResponseJsonapi | Unset):
        links (JSONAPILinks | None | Unset):
    """

    data: CandidateResource
    jsonapi: CandidateSingleResponseJsonapi | Unset = UNSET
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
        from ..models.candidate_resource import CandidateResource
        from ..models.candidate_single_response_jsonapi import (
            CandidateSingleResponseJsonapi,
        )
        from ..models.jsonapi_links import JSONAPILinks

        d = dict(src_dict)
        data = CandidateResource.from_dict(d.pop("data"))

        _jsonapi = d.pop("jsonapi", UNSET)
        jsonapi: CandidateSingleResponseJsonapi | Unset
        if isinstance(_jsonapi, Unset):
            jsonapi = UNSET
        else:
            jsonapi = CandidateSingleResponseJsonapi.from_dict(_jsonapi)

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

        candidate_single_response = cls(
            data=data,
            jsonapi=jsonapi,
            links=links,
        )

        candidate_single_response.additional_properties = d
        return candidate_single_response

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
