from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="NoteStatsAttributes")


@_attrs_define
class NoteStatsAttributes:
    """Attributes for note statistics resource.

    Attributes:
        total_notes (int):
        helpful_notes (int):
        not_helpful_notes (int):
        pending_notes (int):
        average_helpfulness_score (float):
    """

    total_notes: int
    helpful_notes: int
    not_helpful_notes: int
    pending_notes: int
    average_helpfulness_score: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_notes = self.total_notes

        helpful_notes = self.helpful_notes

        not_helpful_notes = self.not_helpful_notes

        pending_notes = self.pending_notes

        average_helpfulness_score = self.average_helpfulness_score

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total_notes": total_notes,
                "helpful_notes": helpful_notes,
                "not_helpful_notes": not_helpful_notes,
                "pending_notes": pending_notes,
                "average_helpfulness_score": average_helpfulness_score,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        total_notes = d.pop("total_notes")

        helpful_notes = d.pop("helpful_notes")

        not_helpful_notes = d.pop("not_helpful_notes")

        pending_notes = d.pop("pending_notes")

        average_helpfulness_score = d.pop("average_helpfulness_score")

        note_stats_attributes = cls(
            total_notes=total_notes,
            helpful_notes=helpful_notes,
            not_helpful_notes=not_helpful_notes,
            pending_notes=pending_notes,
            average_helpfulness_score=average_helpfulness_score,
        )

        note_stats_attributes.additional_properties = d
        return note_stats_attributes

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
