from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ConsensusMetricsData")


@_attrs_define
class ConsensusMetricsData:
    """
    Attributes:
        mean_agreement (float):
        polarization_index (float):
        notes_with_consensus (int):
        notes_with_disagreement (int):
        total_notes_rated (int):
    """

    mean_agreement: float
    polarization_index: float
    notes_with_consensus: int
    notes_with_disagreement: int
    total_notes_rated: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mean_agreement = self.mean_agreement

        polarization_index = self.polarization_index

        notes_with_consensus = self.notes_with_consensus

        notes_with_disagreement = self.notes_with_disagreement

        total_notes_rated = self.total_notes_rated

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "mean_agreement": mean_agreement,
                "polarization_index": polarization_index,
                "notes_with_consensus": notes_with_consensus,
                "notes_with_disagreement": notes_with_disagreement,
                "total_notes_rated": total_notes_rated,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        mean_agreement = d.pop("mean_agreement")

        polarization_index = d.pop("polarization_index")

        notes_with_consensus = d.pop("notes_with_consensus")

        notes_with_disagreement = d.pop("notes_with_disagreement")

        total_notes_rated = d.pop("total_notes_rated")

        consensus_metrics_data = cls(
            mean_agreement=mean_agreement,
            polarization_index=polarization_index,
            notes_with_consensus=notes_with_consensus,
            notes_with_disagreement=notes_with_disagreement,
            total_notes_rated=total_notes_rated,
        )

        consensus_metrics_data.additional_properties = d
        return consensus_metrics_data

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
