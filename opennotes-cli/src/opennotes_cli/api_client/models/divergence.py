from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.divergence_direction import DivergenceDirection

T = TypeVar("T", bound="Divergence")


@_attrs_define
class Divergence:
    """
    Attributes:
        direction (DivergenceDirection):
        signal_source (str): Short display-ready source label, such as Text moderation, Web Risk, Image moderation,
            Video moderation, or Combined signals.
        signal_detail (str): Short display-ready description of the adjusted signal.
        reason (str): User-readable reason the raw signal was discounted or escalated.
    """

    direction: DivergenceDirection
    signal_source: str
    signal_detail: str
    reason: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        direction = self.direction.value

        signal_source = self.signal_source

        signal_detail = self.signal_detail

        reason = self.reason

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "direction": direction,
                "signal_source": signal_source,
                "signal_detail": signal_detail,
                "reason": reason,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        direction = DivergenceDirection(d.pop("direction"))

        signal_source = d.pop("signal_source")

        signal_detail = d.pop("signal_detail")

        reason = d.pop("reason")

        divergence = cls(
            direction=direction,
            signal_source=signal_source,
            signal_detail=signal_detail,
            reason=reason,
        )

        divergence.additional_properties = d
        return divergence

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
