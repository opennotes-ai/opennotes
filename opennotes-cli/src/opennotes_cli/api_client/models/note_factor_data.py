from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="NoteFactorData")


@_attrs_define
class NoteFactorData:
    """
    Attributes:
        note_id (str):
        intercept (float):
        factor1 (float):
        status (None | str):
        classification (None | str):
        author_agent_name (None | str):
    """

    note_id: str
    intercept: float
    factor1: float
    status: None | str
    classification: None | str
    author_agent_name: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        note_id = self.note_id

        intercept = self.intercept

        factor1 = self.factor1

        status: None | str
        status = self.status

        classification: None | str
        classification = self.classification

        author_agent_name: None | str
        author_agent_name = self.author_agent_name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "note_id": note_id,
                "intercept": intercept,
                "factor1": factor1,
                "status": status,
                "classification": classification,
                "author_agent_name": author_agent_name,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        note_id = d.pop("note_id")

        intercept = d.pop("intercept")

        factor1 = d.pop("factor1")

        def _parse_status(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        status = _parse_status(d.pop("status"))

        def _parse_classification(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        classification = _parse_classification(d.pop("classification"))

        def _parse_author_agent_name(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        author_agent_name = _parse_author_agent_name(d.pop("author_agent_name"))

        note_factor_data = cls(
            note_id=note_id,
            intercept=intercept,
            factor1=factor1,
            status=status,
            classification=classification,
            author_agent_name=author_agent_name,
        )

        note_factor_data.additional_properties = d
        return note_factor_data

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
