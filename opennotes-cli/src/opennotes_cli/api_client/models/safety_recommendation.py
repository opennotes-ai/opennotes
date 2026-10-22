from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.safety_level import SafetyLevel
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.divergence import Divergence


T = TypeVar("T", bound="SafetyRecommendation")


@_attrs_define
class SafetyRecommendation:
    """
    Attributes:
        level (SafetyLevel):
        rationale (str):
        top_signals (list[str] | Unset):
        unavailable_inputs (list[str] | Unset):
        divergences (list[Divergence] | Unset):
        display (str | Unset):  Default: ''.
    """

    level: SafetyLevel
    rationale: str
    top_signals: list[str] | Unset = UNSET
    unavailable_inputs: list[str] | Unset = UNSET
    divergences: list[Divergence] | Unset = UNSET
    display: str | Unset = ""
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        level = self.level.value

        rationale = self.rationale

        top_signals: list[str] | Unset = UNSET
        if not isinstance(self.top_signals, Unset):
            top_signals = self.top_signals

        unavailable_inputs: list[str] | Unset = UNSET
        if not isinstance(self.unavailable_inputs, Unset):
            unavailable_inputs = self.unavailable_inputs

        divergences: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.divergences, Unset):
            divergences = []
            for divergences_item_data in self.divergences:
                divergences_item = divergences_item_data.to_dict()
                divergences.append(divergences_item)

        display = self.display

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "level": level,
                "rationale": rationale,
            }
        )
        if top_signals is not UNSET:
            field_dict["top_signals"] = top_signals
        if unavailable_inputs is not UNSET:
            field_dict["unavailable_inputs"] = unavailable_inputs
        if divergences is not UNSET:
            field_dict["divergences"] = divergences
        if display is not UNSET:
            field_dict["display"] = display

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.divergence import Divergence

        d = dict(src_dict)
        level = SafetyLevel(d.pop("level"))

        rationale = d.pop("rationale")

        top_signals = cast(list[str], d.pop("top_signals", UNSET))

        unavailable_inputs = cast(list[str], d.pop("unavailable_inputs", UNSET))

        _divergences = d.pop("divergences", UNSET)
        divergences: list[Divergence] | Unset = UNSET
        if _divergences is not UNSET:
            divergences = []
            for divergences_item_data in _divergences:
                divergences_item = Divergence.from_dict(divergences_item_data)

                divergences.append(divergences_item)

        display = d.pop("display", UNSET)

        safety_recommendation = cls(
            level=level,
            rationale=rationale,
            top_signals=top_signals,
            unavailable_inputs=unavailable_inputs,
            divergences=divergences,
            display=display,
        )

        safety_recommendation.additional_properties = d
        return safety_recommendation

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
