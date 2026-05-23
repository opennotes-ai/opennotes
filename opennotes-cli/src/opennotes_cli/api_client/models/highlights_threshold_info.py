from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="HighlightsThresholdInfo")


@_attrs_define
class HighlightsThresholdInfo:
    """
    Attributes:
        total_authors (int):
        total_utterances (int):
        min_authors_required (int):
        min_occurrences_required (int):
    """

    total_authors: int
    total_utterances: int
    min_authors_required: int
    min_occurrences_required: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_authors = self.total_authors

        total_utterances = self.total_utterances

        min_authors_required = self.min_authors_required

        min_occurrences_required = self.min_occurrences_required

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total_authors": total_authors,
                "total_utterances": total_utterances,
                "min_authors_required": min_authors_required,
                "min_occurrences_required": min_occurrences_required,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        total_authors = d.pop("total_authors")

        total_utterances = d.pop("total_utterances")

        min_authors_required = d.pop("min_authors_required")

        min_occurrences_required = d.pop("min_occurrences_required")

        highlights_threshold_info = cls(
            total_authors=total_authors,
            total_utterances=total_utterances,
            min_authors_required=min_authors_required,
            min_occurrences_required=min_occurrences_required,
        )

        highlights_threshold_info.additional_properties = d
        return highlights_threshold_info

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
