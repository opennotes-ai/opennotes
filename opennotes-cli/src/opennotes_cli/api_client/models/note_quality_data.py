from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.note_quality_data_notes_by_classification import (
        NoteQualityDataNotesByClassification,
    )
    from ..models.note_quality_data_notes_by_status import NoteQualityDataNotesByStatus


T = TypeVar("T", bound="NoteQualityData")


@_attrs_define
class NoteQualityData:
    """
    Attributes:
        avg_helpfulness_score (float | None):
        notes_by_status (NoteQualityDataNotesByStatus):
        notes_by_classification (NoteQualityDataNotesByClassification):
    """

    avg_helpfulness_score: float | None
    notes_by_status: NoteQualityDataNotesByStatus
    notes_by_classification: NoteQualityDataNotesByClassification
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        avg_helpfulness_score: float | None
        avg_helpfulness_score = self.avg_helpfulness_score

        notes_by_status = self.notes_by_status.to_dict()

        notes_by_classification = self.notes_by_classification.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "avg_helpfulness_score": avg_helpfulness_score,
                "notes_by_status": notes_by_status,
                "notes_by_classification": notes_by_classification,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.note_quality_data_notes_by_classification import (
            NoteQualityDataNotesByClassification,
        )
        from ..models.note_quality_data_notes_by_status import (
            NoteQualityDataNotesByStatus,
        )

        d = dict(src_dict)

        def _parse_avg_helpfulness_score(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        avg_helpfulness_score = _parse_avg_helpfulness_score(
            d.pop("avg_helpfulness_score")
        )

        notes_by_status = NoteQualityDataNotesByStatus.from_dict(
            d.pop("notes_by_status")
        )

        notes_by_classification = NoteQualityDataNotesByClassification.from_dict(
            d.pop("notes_by_classification")
        )

        note_quality_data = cls(
            avg_helpfulness_score=avg_helpfulness_score,
            notes_by_status=notes_by_status,
            notes_by_classification=notes_by_classification,
        )

        note_quality_data.additional_properties = d
        return note_quality_data

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
