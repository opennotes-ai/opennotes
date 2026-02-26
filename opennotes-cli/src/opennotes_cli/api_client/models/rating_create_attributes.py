from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

from ..models.helpfulness_level import HelpfulnessLevel

T = TypeVar("T", bound="RatingCreateAttributes")


@_attrs_define
class RatingCreateAttributes:
    """Attributes for creating a rating via JSON:API.

    Attributes:
        note_id (UUID): Note ID to rate
        rater_id (UUID): Rater's user profile ID
        helpfulness_level (HelpfulnessLevel):
    """

    note_id: UUID
    rater_id: UUID
    helpfulness_level: HelpfulnessLevel

    def to_dict(self) -> dict[str, Any]:
        note_id = str(self.note_id)

        rater_id = str(self.rater_id)

        helpfulness_level = self.helpfulness_level.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "note_id": note_id,
                "rater_id": rater_id,
                "helpfulness_level": helpfulness_level,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        note_id = UUID(d.pop("note_id"))

        rater_id = UUID(d.pop("rater_id"))

        helpfulness_level = HelpfulnessLevel(d.pop("helpfulness_level"))

        rating_create_attributes = cls(
            note_id=note_id,
            rater_id=rater_id,
            helpfulness_level=helpfulness_level,
        )

        return rating_create_attributes
