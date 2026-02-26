from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="NoteScoreAttributes")


@_attrs_define
class NoteScoreAttributes:
    """Attributes for note score resource.

    Attributes:
        score (float): Normalized score value (0.0-1.0)
        confidence (str): Confidence level: no_data, provisional, or standard
        algorithm (str): Scoring algorithm used
        rating_count (int): Number of ratings contributing to the score
        tier (int): Current scoring tier level (0-5)
        tier_name (str): Human-readable tier name
        calculated_at (datetime.datetime | None | Unset): Timestamp when score was calculated
        content (None | str | Unset): Message content from archive
    """

    score: float
    confidence: str
    algorithm: str
    rating_count: int
    tier: int
    tier_name: str
    calculated_at: datetime.datetime | None | Unset = UNSET
    content: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        score = self.score

        confidence = self.confidence

        algorithm = self.algorithm

        rating_count = self.rating_count

        tier = self.tier

        tier_name = self.tier_name

        calculated_at: None | str | Unset
        if isinstance(self.calculated_at, Unset):
            calculated_at = UNSET
        elif isinstance(self.calculated_at, datetime.datetime):
            calculated_at = self.calculated_at.isoformat()
        else:
            calculated_at = self.calculated_at

        content: None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        else:
            content = self.content

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "score": score,
                "confidence": confidence,
                "algorithm": algorithm,
                "rating_count": rating_count,
                "tier": tier,
                "tier_name": tier_name,
            }
        )
        if calculated_at is not UNSET:
            field_dict["calculated_at"] = calculated_at
        if content is not UNSET:
            field_dict["content"] = content

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        score = d.pop("score")

        confidence = d.pop("confidence")

        algorithm = d.pop("algorithm")

        rating_count = d.pop("rating_count")

        tier = d.pop("tier")

        tier_name = d.pop("tier_name")

        def _parse_calculated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                calculated_at_type_0 = isoparse(data)

                return calculated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        calculated_at = _parse_calculated_at(d.pop("calculated_at", UNSET))

        def _parse_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))

        note_score_attributes = cls(
            score=score,
            confidence=confidence,
            algorithm=algorithm,
            rating_count=rating_count,
            tier=tier,
            tier_name=tier_name,
            calculated_at=calculated_at,
            content=content,
        )

        note_score_attributes.additional_properties = d
        return note_score_attributes

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
