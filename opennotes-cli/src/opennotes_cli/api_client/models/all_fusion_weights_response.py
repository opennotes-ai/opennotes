from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.all_fusion_weights_response_datasets import (
        AllFusionWeightsResponseDatasets,
    )


T = TypeVar("T", bound="AllFusionWeightsResponse")


@_attrs_define
class AllFusionWeightsResponse:
    """Response model for all fusion weights.

    Attributes:
        default (float): Global default fusion weight
        datasets (AllFusionWeightsResponseDatasets | Unset): Dataset-specific fusion weights
    """

    default: float
    datasets: AllFusionWeightsResponseDatasets | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        default = self.default

        datasets: dict[str, Any] | Unset = UNSET
        if not isinstance(self.datasets, Unset):
            datasets = self.datasets.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "default": default,
            }
        )
        if datasets is not UNSET:
            field_dict["datasets"] = datasets

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.all_fusion_weights_response_datasets import (
            AllFusionWeightsResponseDatasets,
        )

        d = dict(src_dict)
        default = d.pop("default")

        _datasets = d.pop("datasets", UNSET)
        datasets: AllFusionWeightsResponseDatasets | Unset
        if isinstance(_datasets, Unset):
            datasets = UNSET
        else:
            datasets = AllFusionWeightsResponseDatasets.from_dict(_datasets)

        all_fusion_weights_response = cls(
            default=default,
            datasets=datasets,
        )

        all_fusion_weights_response.additional_properties = d
        return all_fusion_weights_response

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
