from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ResumeAttributes")


@_attrs_define
class ResumeAttributes:
    """
    Attributes:
        reset_turns (bool | Unset):  Default: False.
    """

    reset_turns: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        reset_turns = self.reset_turns

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if reset_turns is not UNSET:
            field_dict["reset_turns"] = reset_turns

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        reset_turns = d.pop("reset_turns", UNSET)

        resume_attributes = cls(
            reset_turns=reset_turns,
        )

        return resume_attributes
