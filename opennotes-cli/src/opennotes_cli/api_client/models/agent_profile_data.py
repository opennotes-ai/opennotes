from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agent_profile_data_last_messages_item import (
        AgentProfileDataLastMessagesItem,
    )


T = TypeVar("T", bound="AgentProfileData")


@_attrs_define
class AgentProfileData:
    """
    Attributes:
        agent_instance_id (str):
        agent_name (str):
        personality (str):
        model_name (str):
        memory_compaction_strategy (str):
        turn_count (int):
        state (str):
        token_count (int):
        recent_actions (list[Any] | Unset):
        last_messages (list[AgentProfileDataLastMessagesItem] | Unset):
    """

    agent_instance_id: str
    agent_name: str
    personality: str
    model_name: str
    memory_compaction_strategy: str
    turn_count: int
    state: str
    token_count: int
    recent_actions: list[Any] | Unset = UNSET
    last_messages: list[AgentProfileDataLastMessagesItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agent_instance_id = self.agent_instance_id

        agent_name = self.agent_name

        personality = self.personality

        model_name = self.model_name

        memory_compaction_strategy = self.memory_compaction_strategy

        turn_count = self.turn_count

        state = self.state

        token_count = self.token_count

        recent_actions: list[Any] | Unset = UNSET
        if not isinstance(self.recent_actions, Unset):
            recent_actions = self.recent_actions

        last_messages: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.last_messages, Unset):
            last_messages = []
            for last_messages_item_data in self.last_messages:
                last_messages_item = last_messages_item_data.to_dict()
                last_messages.append(last_messages_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agent_instance_id": agent_instance_id,
                "agent_name": agent_name,
                "personality": personality,
                "model_name": model_name,
                "memory_compaction_strategy": memory_compaction_strategy,
                "turn_count": turn_count,
                "state": state,
                "token_count": token_count,
            }
        )
        if recent_actions is not UNSET:
            field_dict["recent_actions"] = recent_actions
        if last_messages is not UNSET:
            field_dict["last_messages"] = last_messages

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent_profile_data_last_messages_item import (
            AgentProfileDataLastMessagesItem,
        )

        d = dict(src_dict)
        agent_instance_id = d.pop("agent_instance_id")

        agent_name = d.pop("agent_name")

        personality = d.pop("personality")

        model_name = d.pop("model_name")

        memory_compaction_strategy = d.pop("memory_compaction_strategy")

        turn_count = d.pop("turn_count")

        state = d.pop("state")

        token_count = d.pop("token_count")

        recent_actions = cast(list[Any], d.pop("recent_actions", UNSET))

        _last_messages = d.pop("last_messages", UNSET)
        last_messages: list[AgentProfileDataLastMessagesItem] | Unset = UNSET
        if _last_messages is not UNSET:
            last_messages = []
            for last_messages_item_data in _last_messages:
                last_messages_item = AgentProfileDataLastMessagesItem.from_dict(
                    last_messages_item_data
                )

                last_messages.append(last_messages_item)

        agent_profile_data = cls(
            agent_instance_id=agent_instance_id,
            agent_name=agent_name,
            personality=personality,
            model_name=model_name,
            memory_compaction_strategy=memory_compaction_strategy,
            turn_count=turn_count,
            state=state,
            token_count=token_count,
            recent_actions=recent_actions,
            last_messages=last_messages,
        )

        agent_profile_data.additional_properties = d
        return agent_profile_data

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
