from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.detailed_request_data import DetailedRequestData


T = TypeVar("T", bound="RequestVarianceMeta")


@_attrs_define
class RequestVarianceMeta:
    """
    Attributes:
        requests (list[DetailedRequestData] | Unset):
        total_requests (int | Unset):  Default: 0.
    """

    requests: list[DetailedRequestData] | Unset = UNSET
    total_requests: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        requests: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.requests, Unset):
            requests = []
            for requests_item_data in self.requests:
                requests_item = requests_item_data.to_dict()
                requests.append(requests_item)

        total_requests = self.total_requests

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if requests is not UNSET:
            field_dict["requests"] = requests
        if total_requests is not UNSET:
            field_dict["total_requests"] = total_requests

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.detailed_request_data import DetailedRequestData

        d = dict(src_dict)
        _requests = d.pop("requests", UNSET)
        requests: list[DetailedRequestData] | Unset = UNSET
        if _requests is not UNSET:
            requests = []
            for requests_item_data in _requests:
                requests_item = DetailedRequestData.from_dict(requests_item_data)

                requests.append(requests_item)

        total_requests = d.pop("total_requests", UNSET)

        request_variance_meta = cls(
            requests=requests,
            total_requests=total_requests,
        )

        request_variance_meta.additional_properties = d
        return request_variance_meta

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
