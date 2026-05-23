from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.weather_axis_literalsourced_factual_claims_first_person_hearsay_misleading_label import (
    WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleadingLabel,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.weather_axis_alternative_literalsourced_factual_claims_first_person_hearsay_misleading import (
        WeatherAxisAlternativeLiteralsourcedFactualClaimsFirstPersonHearsayMisleading,
    )


T = TypeVar(
    "T", bound="WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleading"
)


@_attrs_define
class WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleading:
    """
    Attributes:
        label (WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleadingLabel):
        logprob (float | None | Unset):
        alternatives (list[WeatherAxisAlternativeLiteralsourcedFactualClaimsFirstPersonHearsayMisleading] | Unset):
    """

    label: WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleadingLabel
    logprob: float | None | Unset = UNSET
    alternatives: (
        list[
            WeatherAxisAlternativeLiteralsourcedFactualClaimsFirstPersonHearsayMisleading
        ]
        | Unset
    ) = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        label = self.label.value

        logprob: float | None | Unset
        if isinstance(self.logprob, Unset):
            logprob = UNSET
        else:
            logprob = self.logprob

        alternatives: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.alternatives, Unset):
            alternatives = []
            for alternatives_item_data in self.alternatives:
                alternatives_item = alternatives_item_data.to_dict()
                alternatives.append(alternatives_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "label": label,
            }
        )
        if logprob is not UNSET:
            field_dict["logprob"] = logprob
        if alternatives is not UNSET:
            field_dict["alternatives"] = alternatives

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.weather_axis_alternative_literalsourced_factual_claims_first_person_hearsay_misleading import (
            WeatherAxisAlternativeLiteralsourcedFactualClaimsFirstPersonHearsayMisleading,
        )

        d = dict(src_dict)
        label = WeatherAxisLiteralsourcedFactualClaimsFirstPersonHearsayMisleadingLabel(
            d.pop("label")
        )

        def _parse_logprob(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        logprob = _parse_logprob(d.pop("logprob", UNSET))

        _alternatives = d.pop("alternatives", UNSET)
        alternatives: (
            list[
                WeatherAxisAlternativeLiteralsourcedFactualClaimsFirstPersonHearsayMisleading
            ]
            | Unset
        ) = UNSET
        if _alternatives is not UNSET:
            alternatives = []
            for alternatives_item_data in _alternatives:
                alternatives_item = WeatherAxisAlternativeLiteralsourcedFactualClaimsFirstPersonHearsayMisleading.from_dict(
                    alternatives_item_data
                )

                alternatives.append(alternatives_item)

        weather_axis_literalsourced_factual_claims_first_person_hearsay_misleading = (
            cls(
                label=label,
                logprob=logprob,
                alternatives=alternatives,
            )
        )

        weather_axis_literalsourced_factual_claims_first_person_hearsay_misleading.additional_properties = d
        return (
            weather_axis_literalsourced_factual_claims_first_person_hearsay_misleading
        )

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
