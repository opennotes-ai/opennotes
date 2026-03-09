from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

if TYPE_CHECKING:
    from ..models.note_factor_data import NoteFactorData
    from ..models.rater_factor_data import RaterFactorData


T = TypeVar("T", bound="ScoringAnalysisAttributes")


@_attrs_define
class ScoringAnalysisAttributes:
    """
    Attributes:
        scored_at (datetime.datetime):
        tier (None | str):
        global_intercept (float):
        rater_count (int):
        note_count (int):
        rater_factors (list[RaterFactorData]):
        note_factors (list[NoteFactorData]):
    """

    scored_at: datetime.datetime
    tier: None | str
    global_intercept: float
    rater_count: int
    note_count: int
    rater_factors: list[RaterFactorData]
    note_factors: list[NoteFactorData]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        scored_at = self.scored_at.isoformat()

        tier: None | str
        tier = self.tier

        global_intercept = self.global_intercept

        rater_count = self.rater_count

        note_count = self.note_count

        rater_factors = []
        for rater_factors_item_data in self.rater_factors:
            rater_factors_item = rater_factors_item_data.to_dict()
            rater_factors.append(rater_factors_item)

        note_factors = []
        for note_factors_item_data in self.note_factors:
            note_factors_item = note_factors_item_data.to_dict()
            note_factors.append(note_factors_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "scored_at": scored_at,
                "tier": tier,
                "global_intercept": global_intercept,
                "rater_count": rater_count,
                "note_count": note_count,
                "rater_factors": rater_factors,
                "note_factors": note_factors,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.note_factor_data import NoteFactorData
        from ..models.rater_factor_data import RaterFactorData

        d = dict(src_dict)
        scored_at = isoparse(d.pop("scored_at"))

        def _parse_tier(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        tier = _parse_tier(d.pop("tier"))

        global_intercept = d.pop("global_intercept")

        rater_count = d.pop("rater_count")

        note_count = d.pop("note_count")

        rater_factors = []
        _rater_factors = d.pop("rater_factors")
        for rater_factors_item_data in _rater_factors:
            rater_factors_item = RaterFactorData.from_dict(rater_factors_item_data)

            rater_factors.append(rater_factors_item)

        note_factors = []
        _note_factors = d.pop("note_factors")
        for note_factors_item_data in _note_factors:
            note_factors_item = NoteFactorData.from_dict(note_factors_item_data)

            note_factors.append(note_factors_item)

        scoring_analysis_attributes = cls(
            scored_at=scored_at,
            tier=tier,
            global_intercept=global_intercept,
            rater_count=rater_count,
            note_count=note_count,
            rater_factors=rater_factors,
            note_factors=note_factors,
        )

        scoring_analysis_attributes.additional_properties = d
        return scoring_analysis_attributes

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
