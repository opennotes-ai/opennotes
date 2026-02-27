from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.orchestrator_create_attributes_scoring_config_type_0 import (
        OrchestratorCreateAttributesScoringConfigType0,
    )


T = TypeVar("T", bound="OrchestratorCreateAttributes")


@_attrs_define
class OrchestratorCreateAttributes:
    """
    Attributes:
        name (str):
        turn_cadence_seconds (int):
        max_agents (int):
        removal_rate (float):
        max_turns_per_agent (int):
        description (None | str | Unset):
        community_server_id (None | Unset | UUID):
        agent_profile_ids (list[str] | Unset):
        scoring_config (None | OrchestratorCreateAttributesScoringConfigType0 | Unset):
    """

    name: str
    turn_cadence_seconds: int
    max_agents: int
    removal_rate: float
    max_turns_per_agent: int
    description: None | str | Unset = UNSET
    community_server_id: None | Unset | UUID = UNSET
    agent_profile_ids: list[str] | Unset = UNSET
    scoring_config: None | OrchestratorCreateAttributesScoringConfigType0 | Unset = (
        UNSET
    )

    def to_dict(self) -> dict[str, Any]:
        from ..models.orchestrator_create_attributes_scoring_config_type_0 import (
            OrchestratorCreateAttributesScoringConfigType0,
        )

        name = self.name

        turn_cadence_seconds = self.turn_cadence_seconds

        max_agents = self.max_agents

        removal_rate = self.removal_rate

        max_turns_per_agent = self.max_turns_per_agent

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

        agent_profile_ids: list[str] | Unset = UNSET
        if not isinstance(self.agent_profile_ids, Unset):
            agent_profile_ids = self.agent_profile_ids

        scoring_config: dict[str, Any] | None | Unset
        if isinstance(self.scoring_config, Unset):
            scoring_config = UNSET
        elif isinstance(
            self.scoring_config, OrchestratorCreateAttributesScoringConfigType0
        ):
            scoring_config = self.scoring_config.to_dict()
        else:
            scoring_config = self.scoring_config

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "turn_cadence_seconds": turn_cadence_seconds,
                "max_agents": max_agents,
                "removal_rate": removal_rate,
                "max_turns_per_agent": max_turns_per_agent,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if community_server_id is not UNSET:
            field_dict["community_server_id"] = community_server_id
        if agent_profile_ids is not UNSET:
            field_dict["agent_profile_ids"] = agent_profile_ids
        if scoring_config is not UNSET:
            field_dict["scoring_config"] = scoring_config

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.orchestrator_create_attributes_scoring_config_type_0 import (
            OrchestratorCreateAttributesScoringConfigType0,
        )

        d = dict(src_dict)
        name = d.pop("name")

        turn_cadence_seconds = d.pop("turn_cadence_seconds")

        max_agents = d.pop("max_agents")

        removal_rate = d.pop("removal_rate")

        max_turns_per_agent = d.pop("max_turns_per_agent")

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

        agent_profile_ids = cast(list[str], d.pop("agent_profile_ids", UNSET))

        def _parse_scoring_config(
            data: object,
        ) -> None | OrchestratorCreateAttributesScoringConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                scoring_config_type_0 = (
                    OrchestratorCreateAttributesScoringConfigType0.from_dict(data)
                )

                return scoring_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None | OrchestratorCreateAttributesScoringConfigType0 | Unset, data
            )

        scoring_config = _parse_scoring_config(d.pop("scoring_config", UNSET))

        orchestrator_create_attributes = cls(
            name=name,
            turn_cadence_seconds=turn_cadence_seconds,
            max_agents=max_agents,
            removal_rate=removal_rate,
            max_turns_per_agent=max_turns_per_agent,
            description=description,
            community_server_id=community_server_id,
            agent_profile_ids=agent_profile_ids,
            scoring_config=scoring_config,
        )

        return orchestrator_create_attributes
