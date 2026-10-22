from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.web_risk_finding_threat_types_item import WebRiskFindingThreatTypesItem

T = TypeVar("T", bound="WebRiskFinding")


@_attrs_define
class WebRiskFinding:
    """
    Attributes:
        url (str):
        threat_types (list[WebRiskFindingThreatTypesItem]):
    """

    url: str
    threat_types: list[WebRiskFindingThreatTypesItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        url = self.url

        threat_types = []
        for threat_types_item_data in self.threat_types:
            threat_types_item = threat_types_item_data.value
            threat_types.append(threat_types_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "url": url,
                "threat_types": threat_types,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        url = d.pop("url")

        threat_types = []
        _threat_types = d.pop("threat_types")
        for threat_types_item_data in _threat_types:
            threat_types_item = WebRiskFindingThreatTypesItem(threat_types_item_data)

            threat_types.append(threat_types_item)

        web_risk_finding = cls(
            url=url,
            threat_types=threat_types,
        )

        web_risk_finding.additional_properties = d
        return web_risk_finding

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
