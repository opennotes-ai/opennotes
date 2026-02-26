from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.orchestrator_update_attributes_scoring_config_type_0 import (
        OrchestratorUpdateAttributesScoringConfigType0,
    )


T = TypeVar("T", bound="OrchestratorUpdateAttributes")


@_attrs_define
class OrchestratorUpdateAttributes:
    """
    Attributes:
        name (None | str | Unset):
        description (None | str | Unset):
        community_server_id (None | Unset | UUID):
        turn_cadence_seconds (int | None | Unset):
        max_agents (int | None | Unset):
        removal_rate (float | None | Unset):
        max_turns_per_agent (int | None | Unset):
        agent_profile_ids (list[str] | None | Unset):
        scoring_config (None | OrchestratorUpdateAttributesScoringConfigType0 | Unset):
    """

    name: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    community_server_id: None | Unset | UUID = UNSET
    turn_cadence_seconds: int | None | Unset = UNSET
    max_agents: int | None | Unset = UNSET
    removal_rate: float | None | Unset = UNSET
    max_turns_per_agent: int | None | Unset = UNSET
    agent_profile_ids: list[str] | None | Unset = UNSET
    scoring_config: None | OrchestratorUpdateAttributesScoringConfigType0 | Unset = (
        UNSET
    )

    def to_dict(self) -> dict[str, Any]:
        from ..models.orchestrator_update_attributes_scoring_config_type_0 import (
            OrchestratorUpdateAttributesScoringConfigType0,
        )

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        community_server_id: None | str | Unset
        if isinstance(self.community_server_id, Unset):
            community_server_id = UNSET
        elif isinstance(self.community_server_id, UUID):
            community_server_id = str(self.community_server_id)
        else:
            community_server_id = self.community_server_id

        turn_cadence_seconds: int | None | Unset
        if isinstance(self.turn_cadence_seconds, Unset):
            turn_cadence_seconds = UNSET
        else:
            turn_cadence_seconds = self.turn_cadence_seconds

        max_agents: int | None | Unset
        if isinstance(self.max_agents, Unset):
            max_agents = UNSET
        else:
            max_agents = self.max_agents

        removal_rate: float | None | Unset
        if isinstance(self.removal_rate, Unset):
            removal_rate = UNSET
        else:
            removal_rate = self.removal_rate

        max_turns_per_agent: int | None | Unset
        if isinstance(self.max_turns_per_agent, Unset):
            max_turns_per_agent = UNSET
        else:
            max_turns_per_agent = self.max_turns_per_agent

        agent_profile_ids: list[str] | None | Unset
        if isinstance(self.agent_profile_ids, Unset):
            agent_profile_ids = UNSET
        elif isinstance(self.agent_profile_ids, list):
            agent_profile_ids = self.agent_profile_ids

        else:
            agent_profile_ids = self.agent_profile_ids

        scoring_config: dict[str, Any] | None | Unset
        if isinstance(self.scoring_config, Unset):
            scoring_config = UNSET
        elif isinstance(
            self.scoring_config, OrchestratorUpdateAttributesScoringConfigType0
        ):
            scoring_config = self.scoring_config.to_dict()
        else:
            scoring_config = self.scoring_config

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if description is not UNSET:
            field_dict["description"] = description
        if community_server_id is not UNSET:
            field_dict["community_server_id"] = community_server_id
        if turn_cadence_seconds is not UNSET:
            field_dict["turn_cadence_seconds"] = turn_cadence_seconds
        if max_agents is not UNSET:
            field_dict["max_agents"] = max_agents
        if removal_rate is not UNSET:
            field_dict["removal_rate"] = removal_rate
        if max_turns_per_agent is not UNSET:
            field_dict["max_turns_per_agent"] = max_turns_per_agent
        if agent_profile_ids is not UNSET:
            field_dict["agent_profile_ids"] = agent_profile_ids
        if scoring_config is not UNSET:
            field_dict["scoring_config"] = scoring_config

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.orchestrator_update_attributes_scoring_config_type_0 import (
            OrchestratorUpdateAttributesScoringConfigType0,
        )

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_community_server_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                community_server_id_type_0 = UUID(data)

                return community_server_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        community_server_id = _parse_community_server_id(
            d.pop("community_server_id", UNSET)
        )

        def _parse_turn_cadence_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        turn_cadence_seconds = _parse_turn_cadence_seconds(
            d.pop("turn_cadence_seconds", UNSET)
        )

        def _parse_max_agents(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_agents = _parse_max_agents(d.pop("max_agents", UNSET))

        def _parse_removal_rate(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        removal_rate = _parse_removal_rate(d.pop("removal_rate", UNSET))

        def _parse_max_turns_per_agent(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_turns_per_agent = _parse_max_turns_per_agent(
            d.pop("max_turns_per_agent", UNSET)
        )

        def _parse_agent_profile_ids(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                agent_profile_ids_type_0 = cast(list[str], data)

                return agent_profile_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        agent_profile_ids = _parse_agent_profile_ids(d.pop("agent_profile_ids", UNSET))

        def _parse_scoring_config(
            data: object,
        ) -> None | OrchestratorUpdateAttributesScoringConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                scoring_config_type_0 = (
                    OrchestratorUpdateAttributesScoringConfigType0.from_dict(data)
                )

                return scoring_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None | OrchestratorUpdateAttributesScoringConfigType0 | Unset, data
            )

        scoring_config = _parse_scoring_config(d.pop("scoring_config", UNSET))

        orchestrator_update_attributes = cls(
            name=name,
            description=description,
            community_server_id=community_server_id,
            turn_cadence_seconds=turn_cadence_seconds,
            max_agents=max_agents,
            removal_rate=removal_rate,
            max_turns_per_agent=max_turns_per_agent,
            agent_profile_ids=agent_profile_ids,
            scoring_config=scoring_config,
        )

        return orchestrator_update_attributes
