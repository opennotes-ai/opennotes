from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.orchestrator_attributes_scoring_config_type_0 import (
        OrchestratorAttributesScoringConfigType0,
    )


T = TypeVar("T", bound="OrchestratorAttributes")


@_attrs_define
class OrchestratorAttributes:
    """
    Attributes:
        name (str):
        turn_cadence_seconds (int):
        max_agents (int):
        removal_rate (float):
        max_turns_per_agent (int):
        is_active (bool):
        description (None | str | Unset):
        community_server_id (None | str | Unset):
        agent_profile_ids (list[str] | None | Unset):
        scoring_config (None | OrchestratorAttributesScoringConfigType0 | Unset):
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
    """

    name: str
    turn_cadence_seconds: int
    max_agents: int
    removal_rate: float
    max_turns_per_agent: int
    is_active: bool
    description: None | str | Unset = UNSET
    community_server_id: None | str | Unset = UNSET
    agent_profile_ids: list[str] | None | Unset = UNSET
    scoring_config: None | OrchestratorAttributesScoringConfigType0 | Unset = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.orchestrator_attributes_scoring_config_type_0 import (
            OrchestratorAttributesScoringConfigType0,
        )

        name = self.name

        turn_cadence_seconds = self.turn_cadence_seconds

        max_agents = self.max_agents

        removal_rate = self.removal_rate

        max_turns_per_agent = self.max_turns_per_agent

        is_active = self.is_active

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        community_server_id: None | str | Unset
        if isinstance(self.community_server_id, Unset):
            community_server_id = UNSET
        else:
            community_server_id = self.community_server_id

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
        elif isinstance(self.scoring_config, OrchestratorAttributesScoringConfigType0):
            scoring_config = self.scoring_config.to_dict()
        else:
            scoring_config = self.scoring_config

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "turn_cadence_seconds": turn_cadence_seconds,
                "max_agents": max_agents,
                "removal_rate": removal_rate,
                "max_turns_per_agent": max_turns_per_agent,
                "is_active": is_active,
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
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.orchestrator_attributes_scoring_config_type_0 import (
            OrchestratorAttributesScoringConfigType0,
        )

        d = dict(src_dict)
        name = d.pop("name")

        turn_cadence_seconds = d.pop("turn_cadence_seconds")

        max_agents = d.pop("max_agents")

        removal_rate = d.pop("removal_rate")

        max_turns_per_agent = d.pop("max_turns_per_agent")

        is_active = d.pop("is_active")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_community_server_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        community_server_id = _parse_community_server_id(
            d.pop("community_server_id", UNSET)
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
        ) -> None | OrchestratorAttributesScoringConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                scoring_config_type_0 = (
                    OrchestratorAttributesScoringConfigType0.from_dict(data)
                )

                return scoring_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OrchestratorAttributesScoringConfigType0 | Unset, data)

        scoring_config = _parse_scoring_config(d.pop("scoring_config", UNSET))

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        orchestrator_attributes = cls(
            name=name,
            turn_cadence_seconds=turn_cadence_seconds,
            max_agents=max_agents,
            removal_rate=removal_rate,
            max_turns_per_agent=max_turns_per_agent,
            is_active=is_active,
            description=description,
            community_server_id=community_server_id,
            agent_profile_ids=agent_profile_ids,
            scoring_config=scoring_config,
            created_at=created_at,
            updated_at=updated_at,
        )

        orchestrator_attributes.additional_properties = d
        return orchestrator_attributes

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
