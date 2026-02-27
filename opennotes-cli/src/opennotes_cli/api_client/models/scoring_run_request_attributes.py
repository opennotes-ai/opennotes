from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.enrollment_data import EnrollmentData
    from ..models.note_data import NoteData
    from ..models.rating_data import RatingData
    from ..models.scoring_run_request_attributes_status_type_0_item import (
        ScoringRunRequestAttributesStatusType0Item,
    )


T = TypeVar("T", bound="ScoringRunRequestAttributes")


@_attrs_define
class ScoringRunRequestAttributes:
    """Attributes for scoring run request via JSON:API.

    Attributes:
        notes (list[NoteData]): List of community notes to score
        ratings (list[RatingData]): List of ratings for the notes
        enrollment (list[EnrollmentData]): List of user enrollment data
        status (list[ScoringRunRequestAttributesStatusType0Item] | None | Unset): Optional note status history
    """

    notes: list[NoteData]
    ratings: list[RatingData]
    enrollment: list[EnrollmentData]
    status: list[ScoringRunRequestAttributesStatusType0Item] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        notes = []
        for notes_item_data in self.notes:
            notes_item = notes_item_data.to_dict()
            notes.append(notes_item)

        ratings = []
        for ratings_item_data in self.ratings:
            ratings_item = ratings_item_data.to_dict()
            ratings.append(ratings_item)

        enrollment = []
        for enrollment_item_data in self.enrollment:
            enrollment_item = enrollment_item_data.to_dict()
            enrollment.append(enrollment_item)

        status: list[dict[str, Any]] | None | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        elif isinstance(self.status, list):
            status = []
            for status_type_0_item_data in self.status:
                status_type_0_item = status_type_0_item_data.to_dict()
                status.append(status_type_0_item)

        else:
            status = self.status

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "notes": notes,
                "ratings": ratings,
                "enrollment": enrollment,
            }
        )
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.enrollment_data import EnrollmentData
        from ..models.note_data import NoteData
        from ..models.rating_data import RatingData
        from ..models.scoring_run_request_attributes_status_type_0_item import (
            ScoringRunRequestAttributesStatusType0Item,
        )

        d = dict(src_dict)
        notes = []
        _notes = d.pop("notes")
        for notes_item_data in _notes:
            notes_item = NoteData.from_dict(notes_item_data)

            notes.append(notes_item)

        ratings = []
        _ratings = d.pop("ratings")
        for ratings_item_data in _ratings:
            ratings_item = RatingData.from_dict(ratings_item_data)

            ratings.append(ratings_item)

        enrollment = []
        _enrollment = d.pop("enrollment")
        for enrollment_item_data in _enrollment:
            enrollment_item = EnrollmentData.from_dict(enrollment_item_data)

            enrollment.append(enrollment_item)

        def _parse_status(
            data: object,
        ) -> list[ScoringRunRequestAttributesStatusType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                status_type_0 = []
                _status_type_0 = data
                for status_type_0_item_data in _status_type_0:
                    status_type_0_item = (
                        ScoringRunRequestAttributesStatusType0Item.from_dict(
                            status_type_0_item_data
                        )
                    )

                    status_type_0.append(status_type_0_item)

                return status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[ScoringRunRequestAttributesStatusType0Item] | None | Unset, data
            )

        status = _parse_status(d.pop("status", UNSET))

        scoring_run_request_attributes = cls(
            notes=notes,
            ratings=ratings,
            enrollment=enrollment,
            status=status,
        )

        return scoring_run_request_attributes
