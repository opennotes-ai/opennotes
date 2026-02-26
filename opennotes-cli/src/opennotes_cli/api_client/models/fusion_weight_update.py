from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="FusionWeightUpdate")


@_attrs_define
class FusionWeightUpdate:
    """Request model for updating fusion weight.

    Attributes:
        alpha (float): Fusion weight alpha ∈ [0, 1]. alpha=1.0 is pure semantic, alpha=0.0 is pure keyword.
        dataset (None | str | Unset): Optional dataset name for dataset-specific override. None for global default.
    """

    alpha: float
    dataset: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        alpha = self.alpha

        dataset: None | str | Unset
        if isinstance(self.dataset, Unset):
            dataset = UNSET
        else:
            dataset = self.dataset

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "alpha": alpha,
            }
        )
        if dataset is not UNSET:
            field_dict["dataset"] = dataset

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        alpha = d.pop("alpha")

        def _parse_dataset(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dataset = _parse_dataset(d.pop("dataset", UNSET))

        fusion_weight_update = cls(
            alpha=alpha,
            dataset=dataset,
        )

        return fusion_weight_update
