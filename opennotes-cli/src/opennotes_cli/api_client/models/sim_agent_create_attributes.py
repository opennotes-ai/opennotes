from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.sim_agent_create_attributes_memory_compaction_config_type_0 import (
        SimAgentCreateAttributesMemoryCompactionConfigType0,
    )
    from ..models.sim_agent_create_attributes_model_params_type_0 import (
        SimAgentCreateAttributesModelParamsType0,
    )
    from ..models.sim_agent_create_attributes_tool_config_type_0 import (
        SimAgentCreateAttributesToolConfigType0,
    )


T = TypeVar("T", bound="SimAgentCreateAttributes")


@_attrs_define
class SimAgentCreateAttributes:
    """
    Attributes:
        name (str):
        personality (str):
        model_name (str):
        model_params (None | SimAgentCreateAttributesModelParamsType0 | Unset):
        tool_config (None | SimAgentCreateAttributesToolConfigType0 | Unset):
        memory_compaction_strategy (None | str | Unset):
        memory_compaction_config (None | SimAgentCreateAttributesMemoryCompactionConfigType0 | Unset):
    """

    name: str
    personality: str
    model_name: str
    model_params: None | SimAgentCreateAttributesModelParamsType0 | Unset = UNSET
    tool_config: None | SimAgentCreateAttributesToolConfigType0 | Unset = UNSET
    memory_compaction_strategy: None | str | Unset = UNSET
    memory_compaction_config: (
        None | SimAgentCreateAttributesMemoryCompactionConfigType0 | Unset
    ) = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.sim_agent_create_attributes_memory_compaction_config_type_0 import (
            SimAgentCreateAttributesMemoryCompactionConfigType0,
        )
        from ..models.sim_agent_create_attributes_model_params_type_0 import (
            SimAgentCreateAttributesModelParamsType0,
        )
        from ..models.sim_agent_create_attributes_tool_config_type_0 import (
            SimAgentCreateAttributesToolConfigType0,
        )

        name = self.name

        personality = self.personality

        model_name = self.model_name

        model_params: dict[str, Any] | None | Unset
        if isinstance(self.model_params, Unset):
            model_params = UNSET
        elif isinstance(self.model_params, SimAgentCreateAttributesModelParamsType0):
            model_params = self.model_params.to_dict()
        else:
            model_params = self.model_params

        tool_config: dict[str, Any] | None | Unset
        if isinstance(self.tool_config, Unset):
            tool_config = UNSET
        elif isinstance(self.tool_config, SimAgentCreateAttributesToolConfigType0):
            tool_config = self.tool_config.to_dict()
        else:
            tool_config = self.tool_config

        memory_compaction_strategy: None | str | Unset
        if isinstance(self.memory_compaction_strategy, Unset):
            memory_compaction_strategy = UNSET
        else:
            memory_compaction_strategy = self.memory_compaction_strategy

        memory_compaction_config: dict[str, Any] | None | Unset
        if isinstance(self.memory_compaction_config, Unset):
            memory_compaction_config = UNSET
        elif isinstance(
            self.memory_compaction_config,
            SimAgentCreateAttributesMemoryCompactionConfigType0,
        ):
            memory_compaction_config = self.memory_compaction_config.to_dict()
        else:
            memory_compaction_config = self.memory_compaction_config

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "personality": personality,
                "model_name": model_name,
            }
        )
        if model_params is not UNSET:
            field_dict["model_params"] = model_params
        if tool_config is not UNSET:
            field_dict["tool_config"] = tool_config
        if memory_compaction_strategy is not UNSET:
            field_dict["memory_compaction_strategy"] = memory_compaction_strategy
        if memory_compaction_config is not UNSET:
            field_dict["memory_compaction_config"] = memory_compaction_config

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.sim_agent_create_attributes_memory_compaction_config_type_0 import (
            SimAgentCreateAttributesMemoryCompactionConfigType0,
        )
        from ..models.sim_agent_create_attributes_model_params_type_0 import (
            SimAgentCreateAttributesModelParamsType0,
        )
        from ..models.sim_agent_create_attributes_tool_config_type_0 import (
            SimAgentCreateAttributesToolConfigType0,
        )

        d = dict(src_dict)
        name = d.pop("name")

        personality = d.pop("personality")

        model_name = d.pop("model_name")

        def _parse_model_params(
            data: object,
        ) -> None | SimAgentCreateAttributesModelParamsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                model_params_type_0 = (
                    SimAgentCreateAttributesModelParamsType0.from_dict(data)
                )

                return model_params_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SimAgentCreateAttributesModelParamsType0 | Unset, data)

        model_params = _parse_model_params(d.pop("model_params", UNSET))

        def _parse_tool_config(
            data: object,
        ) -> None | SimAgentCreateAttributesToolConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                tool_config_type_0 = SimAgentCreateAttributesToolConfigType0.from_dict(
                    data
                )

                return tool_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SimAgentCreateAttributesToolConfigType0 | Unset, data)

        tool_config = _parse_tool_config(d.pop("tool_config", UNSET))

        def _parse_memory_compaction_strategy(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        memory_compaction_strategy = _parse_memory_compaction_strategy(
            d.pop("memory_compaction_strategy", UNSET)
        )

        def _parse_memory_compaction_config(
            data: object,
        ) -> None | SimAgentCreateAttributesMemoryCompactionConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                memory_compaction_config_type_0 = (
                    SimAgentCreateAttributesMemoryCompactionConfigType0.from_dict(data)
                )

                return memory_compaction_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None | SimAgentCreateAttributesMemoryCompactionConfigType0 | Unset, data
            )

        memory_compaction_config = _parse_memory_compaction_config(
            d.pop("memory_compaction_config", UNSET)
        )

        sim_agent_create_attributes = cls(
            name=name,
            personality=personality,
            model_name=model_name,
            model_params=model_params,
            tool_config=tool_config,
            memory_compaction_strategy=memory_compaction_strategy,
            memory_compaction_config=memory_compaction_config,
        )

        return sim_agent_create_attributes
