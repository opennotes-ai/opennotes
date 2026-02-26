from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.model_name_response import ModelNameResponse
    from ..models.sim_agent_attributes_memory_compaction_config_type_0 import (
        SimAgentAttributesMemoryCompactionConfigType0,
    )
    from ..models.sim_agent_attributes_model_params_type_0 import (
        SimAgentAttributesModelParamsType0,
    )
    from ..models.sim_agent_attributes_tool_config_type_0 import (
        SimAgentAttributesToolConfigType0,
    )


T = TypeVar("T", bound="SimAgentAttributes")


@_attrs_define
class SimAgentAttributes:
    """
    Attributes:
        name (str):
        personality (str):
        model_name (ModelNameResponse):
        memory_compaction_strategy (str):
        model_params (None | SimAgentAttributesModelParamsType0 | Unset):
        tool_config (None | SimAgentAttributesToolConfigType0 | Unset):
        memory_compaction_config (None | SimAgentAttributesMemoryCompactionConfigType0 | Unset):
        community_server_id (None | str | Unset):
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
    """

    name: str
    personality: str
    model_name: ModelNameResponse
    memory_compaction_strategy: str
    model_params: None | SimAgentAttributesModelParamsType0 | Unset = UNSET
    tool_config: None | SimAgentAttributesToolConfigType0 | Unset = UNSET
    memory_compaction_config: (
        None | SimAgentAttributesMemoryCompactionConfigType0 | Unset
    ) = UNSET
    community_server_id: None | str | Unset = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.sim_agent_attributes_memory_compaction_config_type_0 import (
            SimAgentAttributesMemoryCompactionConfigType0,
        )
        from ..models.sim_agent_attributes_model_params_type_0 import (
            SimAgentAttributesModelParamsType0,
        )
        from ..models.sim_agent_attributes_tool_config_type_0 import (
            SimAgentAttributesToolConfigType0,
        )

        name = self.name

        personality = self.personality

        model_name = self.model_name.to_dict()

        memory_compaction_strategy = self.memory_compaction_strategy

        model_params: dict[str, Any] | None | Unset
        if isinstance(self.model_params, Unset):
            model_params = UNSET
        elif isinstance(self.model_params, SimAgentAttributesModelParamsType0):
            model_params = self.model_params.to_dict()
        else:
            model_params = self.model_params

        tool_config: dict[str, Any] | None | Unset
        if isinstance(self.tool_config, Unset):
            tool_config = UNSET
        elif isinstance(self.tool_config, SimAgentAttributesToolConfigType0):
            tool_config = self.tool_config.to_dict()
        else:
            tool_config = self.tool_config

        memory_compaction_config: dict[str, Any] | None | Unset
        if isinstance(self.memory_compaction_config, Unset):
            memory_compaction_config = UNSET
        elif isinstance(
            self.memory_compaction_config, SimAgentAttributesMemoryCompactionConfigType0
        ):
            memory_compaction_config = self.memory_compaction_config.to_dict()
        else:
            memory_compaction_config = self.memory_compaction_config

        community_server_id: None | str | Unset
        if isinstance(self.community_server_id, Unset):
            community_server_id = UNSET
        else:
            community_server_id = self.community_server_id

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
                "personality": personality,
                "model_name": model_name,
                "memory_compaction_strategy": memory_compaction_strategy,
            }
        )
        if model_params is not UNSET:
            field_dict["model_params"] = model_params
        if tool_config is not UNSET:
            field_dict["tool_config"] = tool_config
        if memory_compaction_config is not UNSET:
            field_dict["memory_compaction_config"] = memory_compaction_config
        if community_server_id is not UNSET:
            field_dict["community_server_id"] = community_server_id
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.model_name_response import ModelNameResponse
        from ..models.sim_agent_attributes_memory_compaction_config_type_0 import (
            SimAgentAttributesMemoryCompactionConfigType0,
        )
        from ..models.sim_agent_attributes_model_params_type_0 import (
            SimAgentAttributesModelParamsType0,
        )
        from ..models.sim_agent_attributes_tool_config_type_0 import (
            SimAgentAttributesToolConfigType0,
        )

        d = dict(src_dict)
        name = d.pop("name")

        personality = d.pop("personality")

        model_name = ModelNameResponse.from_dict(d.pop("model_name"))

        memory_compaction_strategy = d.pop("memory_compaction_strategy")

        def _parse_model_params(
            data: object,
        ) -> None | SimAgentAttributesModelParamsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                model_params_type_0 = SimAgentAttributesModelParamsType0.from_dict(data)

                return model_params_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SimAgentAttributesModelParamsType0 | Unset, data)

        model_params = _parse_model_params(d.pop("model_params", UNSET))

        def _parse_tool_config(
            data: object,
        ) -> None | SimAgentAttributesToolConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                tool_config_type_0 = SimAgentAttributesToolConfigType0.from_dict(data)

                return tool_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SimAgentAttributesToolConfigType0 | Unset, data)

        tool_config = _parse_tool_config(d.pop("tool_config", UNSET))

        def _parse_memory_compaction_config(
            data: object,
        ) -> None | SimAgentAttributesMemoryCompactionConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                memory_compaction_config_type_0 = (
                    SimAgentAttributesMemoryCompactionConfigType0.from_dict(data)
                )

                return memory_compaction_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None | SimAgentAttributesMemoryCompactionConfigType0 | Unset, data
            )

        memory_compaction_config = _parse_memory_compaction_config(
            d.pop("memory_compaction_config", UNSET)
        )

        def _parse_community_server_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        community_server_id = _parse_community_server_id(
            d.pop("community_server_id", UNSET)
        )

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

        sim_agent_attributes = cls(
            name=name,
            personality=personality,
            model_name=model_name,
            memory_compaction_strategy=memory_compaction_strategy,
            model_params=model_params,
            tool_config=tool_config,
            memory_compaction_config=memory_compaction_config,
            community_server_id=community_server_id,
            created_at=created_at,
            updated_at=updated_at,
        )

        sim_agent_attributes.additional_properties = d
        return sim_agent_attributes

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
