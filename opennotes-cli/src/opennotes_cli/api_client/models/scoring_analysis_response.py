from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.scoring_analysis_resource import ScoringAnalysisResource
    from ..models.scoring_analysis_response_jsonapi import (
        ScoringAnalysisResponseJsonapi,
    )


T = TypeVar("T", bound="ScoringAnalysisResponse")


@_attrs_define
class ScoringAnalysisResponse:
    """
    Attributes:
        data (ScoringAnalysisResource):
        jsonapi (ScoringAnalysisResponseJsonapi | Unset):
    """

    data: ScoringAnalysisResource
    jsonapi: ScoringAnalysisResponseJsonapi | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = self.data.to_dict()

        jsonapi: dict[str, Any] | Unset = UNSET
        if not isinstance(self.jsonapi, Unset):
            jsonapi = self.jsonapi.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data": data,
            }
        )
        if jsonapi is not UNSET:
            field_dict["jsonapi"] = jsonapi

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.scoring_analysis_resource import ScoringAnalysisResource
        from ..models.scoring_analysis_response_jsonapi import (
            ScoringAnalysisResponseJsonapi,
        )

        d = dict(src_dict)
        data = ScoringAnalysisResource.from_dict(d.pop("data"))

        _jsonapi = d.pop("jsonapi", UNSET)
        jsonapi: ScoringAnalysisResponseJsonapi | Unset
        if isinstance(_jsonapi, Unset):
            jsonapi = UNSET
        else:
            jsonapi = ScoringAnalysisResponseJsonapi.from_dict(_jsonapi)

        scoring_analysis_response = cls(
            data=data,
            jsonapi=jsonapi,
        )

        scoring_analysis_response.additional_properties = d
        return scoring_analysis_response

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
