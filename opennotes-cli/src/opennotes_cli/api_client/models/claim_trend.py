from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ClaimTrend")


@_attrs_define
class ClaimTrend:
    """
    Attributes:
        label (str):
        cluster_texts (list[str]):
        summary (str):
    """

    label: str
    cluster_texts: list[str]
    summary: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        label = self.label

        cluster_texts = self.cluster_texts

        summary = self.summary

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "label": label,
                "cluster_texts": cluster_texts,
                "summary": summary,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        label = d.pop("label")

        cluster_texts = cast(list[str], d.pop("cluster_texts"))

        summary = d.pop("summary")

        claim_trend = cls(
            label=label,
            cluster_texts=cluster_texts,
            summary=summary,
        )

        claim_trend.additional_properties = d
        return claim_trend

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
