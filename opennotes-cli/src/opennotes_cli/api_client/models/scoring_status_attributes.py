from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.next_tier_info import NextTierInfo
    from ..models.performance_metrics import PerformanceMetrics
    from ..models.scoring_status_attributes_configuration import (
        ScoringStatusAttributesConfiguration,
    )
    from ..models.scoring_status_attributes_tier_thresholds import (
        ScoringStatusAttributesTierThresholds,
    )
    from ..models.tier_info import TierInfo


T = TypeVar("T", bound="ScoringStatusAttributes")


@_attrs_define
class ScoringStatusAttributes:
    """Attributes for scoring status resource.

    Attributes:
        current_note_count (int): Current total number of notes in the system
        active_tier (TierInfo):
        data_confidence (str): Confidence level in scoring results
        tier_thresholds (ScoringStatusAttributesTierThresholds): Threshold information for all tiers
        performance_metrics (PerformanceMetrics):
        next_tier_upgrade (NextTierInfo | None | Unset): Information about the next tier upgrade
        warnings (list[str] | Unset): Any warnings about data quality
        configuration (ScoringStatusAttributesConfiguration | Unset): Current scoring configuration
    """

    current_note_count: int
    active_tier: TierInfo
    data_confidence: str
    tier_thresholds: ScoringStatusAttributesTierThresholds
    performance_metrics: PerformanceMetrics
    next_tier_upgrade: NextTierInfo | None | Unset = UNSET
    warnings: list[str] | Unset = UNSET
    configuration: ScoringStatusAttributesConfiguration | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.next_tier_info import NextTierInfo

        current_note_count = self.current_note_count

        active_tier = self.active_tier.to_dict()

        data_confidence = self.data_confidence

        tier_thresholds = self.tier_thresholds.to_dict()

        performance_metrics = self.performance_metrics.to_dict()

        next_tier_upgrade: dict[str, Any] | None | Unset
        if isinstance(self.next_tier_upgrade, Unset):
            next_tier_upgrade = UNSET
        elif isinstance(self.next_tier_upgrade, NextTierInfo):
            next_tier_upgrade = self.next_tier_upgrade.to_dict()
        else:
            next_tier_upgrade = self.next_tier_upgrade

        warnings: list[str] | Unset = UNSET
        if not isinstance(self.warnings, Unset):
            warnings = self.warnings

        configuration: dict[str, Any] | Unset = UNSET
        if not isinstance(self.configuration, Unset):
            configuration = self.configuration.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "current_note_count": current_note_count,
                "active_tier": active_tier,
                "data_confidence": data_confidence,
                "tier_thresholds": tier_thresholds,
                "performance_metrics": performance_metrics,
            }
        )
        if next_tier_upgrade is not UNSET:
            field_dict["next_tier_upgrade"] = next_tier_upgrade
        if warnings is not UNSET:
            field_dict["warnings"] = warnings
        if configuration is not UNSET:
            field_dict["configuration"] = configuration

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.next_tier_info import NextTierInfo
        from ..models.performance_metrics import PerformanceMetrics
        from ..models.scoring_status_attributes_configuration import (
            ScoringStatusAttributesConfiguration,
        )
        from ..models.scoring_status_attributes_tier_thresholds import (
            ScoringStatusAttributesTierThresholds,
        )
        from ..models.tier_info import TierInfo

        d = dict(src_dict)
        current_note_count = d.pop("current_note_count")

        active_tier = TierInfo.from_dict(d.pop("active_tier"))

        data_confidence = d.pop("data_confidence")

        tier_thresholds = ScoringStatusAttributesTierThresholds.from_dict(
            d.pop("tier_thresholds")
        )

        performance_metrics = PerformanceMetrics.from_dict(d.pop("performance_metrics"))

        def _parse_next_tier_upgrade(data: object) -> NextTierInfo | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                next_tier_upgrade_type_0 = NextTierInfo.from_dict(data)

                return next_tier_upgrade_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(NextTierInfo | None | Unset, data)

        next_tier_upgrade = _parse_next_tier_upgrade(d.pop("next_tier_upgrade", UNSET))

        warnings = cast(list[str], d.pop("warnings", UNSET))

        _configuration = d.pop("configuration", UNSET)
        configuration: ScoringStatusAttributesConfiguration | Unset
        if isinstance(_configuration, Unset):
            configuration = UNSET
        else:
            configuration = ScoringStatusAttributesConfiguration.from_dict(
                _configuration
            )

        scoring_status_attributes = cls(
            current_note_count=current_note_count,
            active_tier=active_tier,
            data_confidence=data_confidence,
            tier_thresholds=tier_thresholds,
            performance_metrics=performance_metrics,
            next_tier_upgrade=next_tier_upgrade,
            warnings=warnings,
            configuration=configuration,
        )

        scoring_status_attributes.additional_properties = d
        return scoring_status_attributes

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
