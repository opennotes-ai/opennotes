from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.request_variance_meta import RequestVarianceMeta


T = TypeVar("T", bound="DetailedAnalysisMeta")


@_attrs_define
class DetailedAnalysisMeta:
    """
    Attributes:
        count (int | Unset):  Default: 0.
        request_variance (RequestVarianceMeta | Unset):
    """

    count: int | Unset = 0
    request_variance: RequestVarianceMeta | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        request_variance: dict[str, Any] | Unset = UNSET
        if not isinstance(self.request_variance, Unset):
            request_variance = self.request_variance.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if count is not UNSET:
            field_dict["count"] = count
        if request_variance is not UNSET:
            field_dict["request_variance"] = request_variance

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.request_variance_meta import RequestVarianceMeta

        d = dict(src_dict)
        count = d.pop("count", UNSET)

        _request_variance = d.pop("request_variance", UNSET)
        request_variance: RequestVarianceMeta | Unset
        if isinstance(_request_variance, Unset):
            request_variance = UNSET
        else:
            request_variance = RequestVarianceMeta.from_dict(_request_variance)

        detailed_analysis_meta = cls(
            count=count,
            request_variance=request_variance,
        )

        detailed_analysis_meta.additional_properties = d
        return detailed_analysis_meta

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
