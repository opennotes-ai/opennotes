from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.flashpoint_match import FlashpointMatch
    from ..models.scd_report import SCDReport


T = TypeVar("T", bound="ToneDynamicsSection")


@_attrs_define
class ToneDynamicsSection:
    """
    Attributes:
        scd (SCDReport):
        flashpoint_matches (list[FlashpointMatch] | Unset):
    """

    scd: SCDReport
    flashpoint_matches: list[FlashpointMatch] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        scd = self.scd.to_dict()

        flashpoint_matches: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.flashpoint_matches, Unset):
            flashpoint_matches = []
            for flashpoint_matches_item_data in self.flashpoint_matches:
                flashpoint_matches_item = flashpoint_matches_item_data.to_dict()
                flashpoint_matches.append(flashpoint_matches_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "scd": scd,
            }
        )
        if flashpoint_matches is not UNSET:
            field_dict["flashpoint_matches"] = flashpoint_matches

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.flashpoint_match import FlashpointMatch
        from ..models.scd_report import SCDReport

        d = dict(src_dict)
        scd = SCDReport.from_dict(d.pop("scd"))

        _flashpoint_matches = d.pop("flashpoint_matches", UNSET)
        flashpoint_matches: list[FlashpointMatch] | Unset = UNSET
        if _flashpoint_matches is not UNSET:
            flashpoint_matches = []
            for flashpoint_matches_item_data in _flashpoint_matches:
                flashpoint_matches_item = FlashpointMatch.from_dict(
                    flashpoint_matches_item_data
                )

                flashpoint_matches.append(flashpoint_matches_item)

        tone_dynamics_section = cls(
            scd=scd,
            flashpoint_matches=flashpoint_matches,
        )

        tone_dynamics_section.additional_properties = d
        return tone_dynamics_section

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
