from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.claims_report import ClaimsReport
    from ..models.fact_check_match import FactCheckMatch


T = TypeVar("T", bound="FactsClaimsSection")


@_attrs_define
class FactsClaimsSection:
    """
    Attributes:
        claims_report (ClaimsReport):
        known_misinformation (list[FactCheckMatch] | Unset):
    """

    claims_report: ClaimsReport
    known_misinformation: list[FactCheckMatch] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        claims_report = self.claims_report.to_dict()

        known_misinformation: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.known_misinformation, Unset):
            known_misinformation = []
            for known_misinformation_item_data in self.known_misinformation:
                known_misinformation_item = known_misinformation_item_data.to_dict()
                known_misinformation.append(known_misinformation_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "claims_report": claims_report,
            }
        )
        if known_misinformation is not UNSET:
            field_dict["known_misinformation"] = known_misinformation

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.claims_report import ClaimsReport
        from ..models.fact_check_match import FactCheckMatch

        d = dict(src_dict)
        claims_report = ClaimsReport.from_dict(d.pop("claims_report"))

        _known_misinformation = d.pop("known_misinformation", UNSET)
        known_misinformation: list[FactCheckMatch] | Unset = UNSET
        if _known_misinformation is not UNSET:
            known_misinformation = []
            for known_misinformation_item_data in _known_misinformation:
                known_misinformation_item = FactCheckMatch.from_dict(
                    known_misinformation_item_data
                )

                known_misinformation.append(known_misinformation_item)

        facts_claims_section = cls(
            claims_report=claims_report,
            known_misinformation=known_misinformation,
        )

        facts_claims_section.additional_properties = d
        return facts_claims_section

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
