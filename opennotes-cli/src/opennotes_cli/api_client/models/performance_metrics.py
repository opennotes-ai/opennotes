from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PerformanceMetrics")


@_attrs_define
class PerformanceMetrics:
    """
    Attributes:
        avg_scoring_time_ms (float): Average scoring time in milliseconds
        scorer_success_rate (float): Success rate for scoring operations (0.0-1.0)
        last_scoring_time_ms (float | None | Unset): Last scoring operation time in milliseconds
        total_scoring_operations (int | Unset): Total number of scoring operations performed Default: 0.
        failed_scoring_operations (int | Unset): Number of failed scoring operations Default: 0.
    """

    avg_scoring_time_ms: float
    scorer_success_rate: float
    last_scoring_time_ms: float | None | Unset = UNSET
    total_scoring_operations: int | Unset = 0
    failed_scoring_operations: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        avg_scoring_time_ms = self.avg_scoring_time_ms

        scorer_success_rate = self.scorer_success_rate

        last_scoring_time_ms: float | None | Unset
        if isinstance(self.last_scoring_time_ms, Unset):
            last_scoring_time_ms = UNSET
        else:
            last_scoring_time_ms = self.last_scoring_time_ms

        total_scoring_operations = self.total_scoring_operations

        failed_scoring_operations = self.failed_scoring_operations

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "avg_scoring_time_ms": avg_scoring_time_ms,
                "scorer_success_rate": scorer_success_rate,
            }
        )
        if last_scoring_time_ms is not UNSET:
            field_dict["last_scoring_time_ms"] = last_scoring_time_ms
        if total_scoring_operations is not UNSET:
            field_dict["total_scoring_operations"] = total_scoring_operations
        if failed_scoring_operations is not UNSET:
            field_dict["failed_scoring_operations"] = failed_scoring_operations

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        avg_scoring_time_ms = d.pop("avg_scoring_time_ms")

        scorer_success_rate = d.pop("scorer_success_rate")

        def _parse_last_scoring_time_ms(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        last_scoring_time_ms = _parse_last_scoring_time_ms(
            d.pop("last_scoring_time_ms", UNSET)
        )

        total_scoring_operations = d.pop("total_scoring_operations", UNSET)

        failed_scoring_operations = d.pop("failed_scoring_operations", UNSET)

        performance_metrics = cls(
            avg_scoring_time_ms=avg_scoring_time_ms,
            scorer_success_rate=scorer_success_rate,
            last_scoring_time_ms=last_scoring_time_ms,
            total_scoring_operations=total_scoring_operations,
            failed_scoring_operations=failed_scoring_operations,
        )

        performance_metrics.additional_properties = d
        return performance_metrics

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
