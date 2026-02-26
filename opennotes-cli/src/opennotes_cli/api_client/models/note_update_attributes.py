from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.note_classification import NoteClassification
from ..types import UNSET, Unset

T = TypeVar("T", bound="NoteUpdateAttributes")


@_attrs_define
class NoteUpdateAttributes:
    """Attributes for updating a note via JSON:API.

    Attributes:
        summary (None | str | Unset): Updated note summary
        classification (None | NoteClassification | Unset): Updated classification
    """

    summary: None | str | Unset = UNSET
    classification: None | NoteClassification | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        summary: None | str | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        else:
            summary = self.summary

        classification: None | str | Unset
        if isinstance(self.classification, Unset):
            classification = UNSET
        elif isinstance(self.classification, NoteClassification):
            classification = self.classification.value
        else:
            classification = self.classification

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if summary is not UNSET:
            field_dict["summary"] = summary
        if classification is not UNSET:
            field_dict["classification"] = classification

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        def _parse_classification(data: object) -> None | NoteClassification | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                classification_type_0 = NoteClassification(data)

                return classification_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | NoteClassification | Unset, data)

        classification = _parse_classification(d.pop("classification", UNSET))

        note_update_attributes = cls(
            summary=summary,
            classification=classification,
        )

        return note_update_attributes
