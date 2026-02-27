from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ProgressAttributes")


@_attrs_define
class ProgressAttributes:
    """
    Attributes:
        turns_completed (int | Unset):  Default: 0.
        turns_errored (int | Unset):  Default: 0.
        notes_written (int | Unset):  Default: 0.
        ratings_given (int | Unset):  Default: 0.
        active_agents (int | Unset):  Default: 0.
    """

    turns_completed: int | Unset = 0
    turns_errored: int | Unset = 0
    notes_written: int | Unset = 0
    ratings_given: int | Unset = 0
    active_agents: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        turns_completed = self.turns_completed

        turns_errored = self.turns_errored

        notes_written = self.notes_written

        ratings_given = self.ratings_given

        active_agents = self.active_agents

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if turns_completed is not UNSET:
            field_dict["turns_completed"] = turns_completed
        if turns_errored is not UNSET:
            field_dict["turns_errored"] = turns_errored
        if notes_written is not UNSET:
            field_dict["notes_written"] = notes_written
        if ratings_given is not UNSET:
            field_dict["ratings_given"] = ratings_given
        if active_agents is not UNSET:
            field_dict["active_agents"] = active_agents

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        turns_completed = d.pop("turns_completed", UNSET)

        turns_errored = d.pop("turns_errored", UNSET)

        notes_written = d.pop("notes_written", UNSET)

        ratings_given = d.pop("ratings_given", UNSET)

        active_agents = d.pop("active_agents", UNSET)

        progress_attributes = cls(
            turns_completed=turns_completed,
            turns_errored=turns_errored,
            notes_written=notes_written,
            ratings_given=ratings_given,
            active_agents=active_agents,
        )

        progress_attributes.additional_properties = d
        return progress_attributes

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
