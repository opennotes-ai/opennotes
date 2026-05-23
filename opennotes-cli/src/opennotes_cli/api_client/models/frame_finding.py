from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="FrameFinding")


@_attrs_define
class FrameFinding:
    """
    Attributes:
        frame_offset_ms (int):
        adult (float):
        violence (float):
        racy (float):
        medical (float):
        spoof (float):
        flagged (bool):
        max_likelihood (float):
    """

    frame_offset_ms: int
    adult: float
    violence: float
    racy: float
    medical: float
    spoof: float
    flagged: bool
    max_likelihood: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        frame_offset_ms = self.frame_offset_ms

        adult = self.adult

        violence = self.violence

        racy = self.racy

        medical = self.medical

        spoof = self.spoof

        flagged = self.flagged

        max_likelihood = self.max_likelihood

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "frame_offset_ms": frame_offset_ms,
                "adult": adult,
                "violence": violence,
                "racy": racy,
                "medical": medical,
                "spoof": spoof,
                "flagged": flagged,
                "max_likelihood": max_likelihood,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        frame_offset_ms = d.pop("frame_offset_ms")

        adult = d.pop("adult")

        violence = d.pop("violence")

        racy = d.pop("racy")

        medical = d.pop("medical")

        spoof = d.pop("spoof")

        flagged = d.pop("flagged")

        max_likelihood = d.pop("max_likelihood")

        frame_finding = cls(
            frame_offset_ms=frame_offset_ms,
            adult=adult,
            violence=violence,
            racy=racy,
            medical=medical,
            spoof=spoof,
            flagged=flagged,
            max_likelihood=max_likelihood,
        )

        frame_finding.additional_properties = d
        return frame_finding

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
