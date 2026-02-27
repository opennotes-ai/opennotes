from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.per_agent_rating_data_distribution import (
        PerAgentRatingDataDistribution,
    )


T = TypeVar("T", bound="PerAgentRatingData")


@_attrs_define
class PerAgentRatingData:
    """
    Attributes:
        agent_instance_id (str):
        agent_name (str):
        distribution (PerAgentRatingDataDistribution):
        total (int):
    """

    agent_instance_id: str
    agent_name: str
    distribution: PerAgentRatingDataDistribution
    total: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agent_instance_id = self.agent_instance_id

        agent_name = self.agent_name

        distribution = self.distribution.to_dict()

        total = self.total

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agent_instance_id": agent_instance_id,
                "agent_name": agent_name,
                "distribution": distribution,
                "total": total,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.per_agent_rating_data_distribution import (
            PerAgentRatingDataDistribution,
        )

        d = dict(src_dict)
        agent_instance_id = d.pop("agent_instance_id")

        agent_name = d.pop("agent_name")

        distribution = PerAgentRatingDataDistribution.from_dict(d.pop("distribution"))

        total = d.pop("total")

        per_agent_rating_data = cls(
            agent_instance_id=agent_instance_id,
            agent_name=agent_name,
            distribution=distribution,
            total=total,
        )

        per_agent_rating_data.additional_properties = d
        return per_agent_rating_data

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
