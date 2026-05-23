from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.web_risk_finding import WebRiskFinding


T = TypeVar("T", bound="WebRiskSection")


@_attrs_define
class WebRiskSection:
    """
    Attributes:
        findings (list[WebRiskFinding] | Unset):
        urls_checked (int | Unset): Number of unique URLs evaluated by Web Risk Default: 0.
    """

    findings: list[WebRiskFinding] | Unset = UNSET
    urls_checked: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        findings: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.findings, Unset):
            findings = []
            for findings_item_data in self.findings:
                findings_item = findings_item_data.to_dict()
                findings.append(findings_item)

        urls_checked = self.urls_checked

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if findings is not UNSET:
            field_dict["findings"] = findings
        if urls_checked is not UNSET:
            field_dict["urls_checked"] = urls_checked

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.web_risk_finding import WebRiskFinding

        d = dict(src_dict)
        _findings = d.pop("findings", UNSET)
        findings: list[WebRiskFinding] | Unset = UNSET
        if _findings is not UNSET:
            findings = []
            for findings_item_data in _findings:
                findings_item = WebRiskFinding.from_dict(findings_item_data)

                findings.append(findings_item)

        urls_checked = d.pop("urls_checked", UNSET)

        web_risk_section = cls(
            findings=findings,
            urls_checked=urls_checked,
        )

        web_risk_section.additional_properties = d
        return web_risk_section

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
