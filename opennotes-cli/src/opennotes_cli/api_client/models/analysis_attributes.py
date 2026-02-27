from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_behavior_data import AgentBehaviorData
    from ..models.consensus_metrics_data import ConsensusMetricsData
    from ..models.note_quality_data import NoteQualityData
    from ..models.rating_distribution_data import RatingDistributionData
    from ..models.scoring_coverage_data import ScoringCoverageData


T = TypeVar("T", bound="AnalysisAttributes")


@_attrs_define
class AnalysisAttributes:
    """
    Attributes:
        rating_distribution (RatingDistributionData):
        consensus_metrics (ConsensusMetricsData):
        scoring_coverage (ScoringCoverageData):
        agent_behaviors (list[AgentBehaviorData]):
        note_quality (NoteQualityData):
    """

    rating_distribution: RatingDistributionData
    consensus_metrics: ConsensusMetricsData
    scoring_coverage: ScoringCoverageData
    agent_behaviors: list[AgentBehaviorData]
    note_quality: NoteQualityData
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rating_distribution = self.rating_distribution.to_dict()

        consensus_metrics = self.consensus_metrics.to_dict()

        scoring_coverage = self.scoring_coverage.to_dict()

        agent_behaviors = []
        for agent_behaviors_item_data in self.agent_behaviors:
            agent_behaviors_item = agent_behaviors_item_data.to_dict()
            agent_behaviors.append(agent_behaviors_item)

        note_quality = self.note_quality.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rating_distribution": rating_distribution,
                "consensus_metrics": consensus_metrics,
                "scoring_coverage": scoring_coverage,
                "agent_behaviors": agent_behaviors,
                "note_quality": note_quality,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent_behavior_data import AgentBehaviorData
        from ..models.consensus_metrics_data import ConsensusMetricsData
        from ..models.note_quality_data import NoteQualityData
        from ..models.rating_distribution_data import RatingDistributionData
        from ..models.scoring_coverage_data import ScoringCoverageData

        d = dict(src_dict)
        rating_distribution = RatingDistributionData.from_dict(
            d.pop("rating_distribution")
        )

        consensus_metrics = ConsensusMetricsData.from_dict(d.pop("consensus_metrics"))

        scoring_coverage = ScoringCoverageData.from_dict(d.pop("scoring_coverage"))

        agent_behaviors = []
        _agent_behaviors = d.pop("agent_behaviors")
        for agent_behaviors_item_data in _agent_behaviors:
            agent_behaviors_item = AgentBehaviorData.from_dict(
                agent_behaviors_item_data
            )

            agent_behaviors.append(agent_behaviors_item)

        note_quality = NoteQualityData.from_dict(d.pop("note_quality"))

        analysis_attributes = cls(
            rating_distribution=rating_distribution,
            consensus_metrics=consensus_metrics,
            scoring_coverage=scoring_coverage,
            agent_behaviors=agent_behaviors,
            note_quality=note_quality,
        )

        analysis_attributes.additional_properties = d
        return analysis_attributes

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
