from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.helpfulness_level import HelpfulnessLevel

T = TypeVar("T", bound="RatingUpdateAttributes")


@_attrs_define
class RatingUpdateAttributes:
    """Attributes for updating a rating via JSON:API.

    Attributes:
        helpfulness_level (HelpfulnessLevel):
    """

    helpfulness_level: HelpfulnessLevel

    def to_dict(self) -> dict[str, Any]:
        helpfulness_level = self.helpfulness_level.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "helpfulness_level": helpfulness_level,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        helpfulness_level = HelpfulnessLevel(d.pop("helpfulness_level"))

        rating_update_attributes = cls(
            helpfulness_level=helpfulness_level,
        )

        return rating_update_attributes
