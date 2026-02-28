from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.scoring_coverage_data_notes_by_status import (
        ScoringCoverageDataNotesByStatus,
    )
    from ..models.scoring_coverage_data_scorer_breakdown import (
        ScoringCoverageDataScorerBreakdown,
    )
    from ..models.scoring_coverage_data_tier_distribution import (
        ScoringCoverageDataTierDistribution,
    )


T = TypeVar("T", bound="ScoringCoverageData")


@_attrs_define
class ScoringCoverageData:
    """
    Attributes:
        current_tier (str):
        total_scores_computed (int):
        tier_distribution (ScoringCoverageDataTierDistribution):
        scorer_breakdown (ScoringCoverageDataScorerBreakdown):
        notes_by_status (ScoringCoverageDataNotesByStatus):
        tiers_reached (list[str]):
        scorers_exercised (list[str]):
    """

    current_tier: str
    total_scores_computed: int
    tier_distribution: ScoringCoverageDataTierDistribution
    scorer_breakdown: ScoringCoverageDataScorerBreakdown
    notes_by_status: ScoringCoverageDataNotesByStatus
    tiers_reached: list[str]
    scorers_exercised: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        current_tier = self.current_tier

        total_scores_computed = self.total_scores_computed

        tier_distribution = self.tier_distribution.to_dict()

        scorer_breakdown = self.scorer_breakdown.to_dict()

        notes_by_status = self.notes_by_status.to_dict()

        tiers_reached = self.tiers_reached

        scorers_exercised = self.scorers_exercised

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "current_tier": current_tier,
                "total_scores_computed": total_scores_computed,
                "tier_distribution": tier_distribution,
                "scorer_breakdown": scorer_breakdown,
                "notes_by_status": notes_by_status,
                "tiers_reached": tiers_reached,
                "scorers_exercised": scorers_exercised,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.scoring_coverage_data_notes_by_status import (
            ScoringCoverageDataNotesByStatus,
        )
        from ..models.scoring_coverage_data_scorer_breakdown import (
            ScoringCoverageDataScorerBreakdown,
        )
        from ..models.scoring_coverage_data_tier_distribution import (
            ScoringCoverageDataTierDistribution,
        )

        d = dict(src_dict)
        current_tier = d.pop("current_tier")

        total_scores_computed = d.pop("total_scores_computed")

        tier_distribution = ScoringCoverageDataTierDistribution.from_dict(
            d.pop("tier_distribution")
        )

        scorer_breakdown = ScoringCoverageDataScorerBreakdown.from_dict(
            d.pop("scorer_breakdown")
        )

        notes_by_status = ScoringCoverageDataNotesByStatus.from_dict(
            d.pop("notes_by_status")
        )

        tiers_reached = cast(list[str], d.pop("tiers_reached"))

        scorers_exercised = cast(list[str], d.pop("scorers_exercised"))

        scoring_coverage_data = cls(
            current_tier=current_tier,
            total_scores_computed=total_scores_computed,
            tier_distribution=tier_distribution,
            scorer_breakdown=scorer_breakdown,
            notes_by_status=notes_by_status,
            tiers_reached=tiers_reached,
            scorers_exercised=scorers_exercised,
        )

        scoring_coverage_data.additional_properties = d
        return scoring_coverage_data

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
