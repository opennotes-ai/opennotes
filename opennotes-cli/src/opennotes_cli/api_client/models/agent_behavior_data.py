from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_behavior_data_action_distribution import (
        AgentBehaviorDataActionDistribution,
    )


T = TypeVar("T", bound="AgentBehaviorData")


@_attrs_define
class AgentBehaviorData:
    """
    Attributes:
        agent_instance_id (str):
        agent_name (str):
        notes_written (int):
        ratings_given (int):
        turn_count (int):
        state (str):
        helpfulness_trend (list[str]):
        action_distribution (AgentBehaviorDataActionDistribution):
    """

    agent_instance_id: str
    agent_name: str
    notes_written: int
    ratings_given: int
    turn_count: int
    state: str
    helpfulness_trend: list[str]
    action_distribution: AgentBehaviorDataActionDistribution
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agent_instance_id = self.agent_instance_id

        agent_name = self.agent_name

        notes_written = self.notes_written

        ratings_given = self.ratings_given

        turn_count = self.turn_count

        state = self.state

        helpfulness_trend = self.helpfulness_trend

        action_distribution = self.action_distribution.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agent_instance_id": agent_instance_id,
                "agent_name": agent_name,
                "notes_written": notes_written,
                "ratings_given": ratings_given,
                "turn_count": turn_count,
                "state": state,
                "helpfulness_trend": helpfulness_trend,
                "action_distribution": action_distribution,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent_behavior_data_action_distribution import (
            AgentBehaviorDataActionDistribution,
        )

        d = dict(src_dict)
        agent_instance_id = d.pop("agent_instance_id")

        agent_name = d.pop("agent_name")

        notes_written = d.pop("notes_written")

        ratings_given = d.pop("ratings_given")

        turn_count = d.pop("turn_count")

        state = d.pop("state")

        helpfulness_trend = cast(list[str], d.pop("helpfulness_trend"))

        action_distribution = AgentBehaviorDataActionDistribution.from_dict(
            d.pop("action_distribution")
        )

        agent_behavior_data = cls(
            agent_instance_id=agent_instance_id,
            agent_name=agent_name,
            notes_written=notes_written,
            ratings_given=ratings_given,
            turn_count=turn_count,
            state=state,
            helpfulness_trend=helpfulness_trend,
            action_distribution=action_distribution,
        )

        agent_behavior_data.additional_properties = d
        return agent_behavior_data

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
