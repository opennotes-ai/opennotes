from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NoteFactorData")


@_attrs_define
class NoteFactorData:
    """
    Attributes:
        note_id (str):
        status (None | str):
        classification (None | str):
        author_agent_name (None | str):
        intercept (float | Unset):  Default: 0.0.
        factor1 (float | Unset):  Default: 0.0.
        author_short_description (None | str | Unset):
    """

    note_id: str
    status: None | str
    classification: None | str
    author_agent_name: None | str
    intercept: float | Unset = 0.0
    factor1: float | Unset = 0.0
    author_short_description: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        note_id = self.note_id

        status: None | str
        status = self.status

        classification: None | str
        classification = self.classification

        author_agent_name: None | str
        author_agent_name = self.author_agent_name

        intercept = self.intercept

        factor1 = self.factor1

        author_short_description: None | str | Unset
        if isinstance(self.author_short_description, Unset):
            author_short_description = UNSET
        else:
            author_short_description = self.author_short_description

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "note_id": note_id,
                "status": status,
                "classification": classification,
                "author_agent_name": author_agent_name,
            }
        )
        if intercept is not UNSET:
            field_dict["intercept"] = intercept
        if factor1 is not UNSET:
            field_dict["factor1"] = factor1
        if author_short_description is not UNSET:
            field_dict["author_short_description"] = author_short_description

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        note_id = d.pop("note_id")

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

        intercept = d.pop("intercept", UNSET)

        factor1 = d.pop("factor1", UNSET)

        def _parse_author_short_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        author_short_description = _parse_author_short_description(
            d.pop("author_short_description", UNSET)
        )

        note_factor_data = cls(
            note_id=note_id,
            status=status,
            classification=classification,
            author_agent_name=author_agent_name,
            intercept=intercept,
            factor1=factor1,
            author_short_description=author_short_description,
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
