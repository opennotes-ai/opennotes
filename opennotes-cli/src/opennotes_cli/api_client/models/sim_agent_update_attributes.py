from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.sim_agent_update_attributes_memory_compaction_config_type_0 import (
        SimAgentUpdateAttributesMemoryCompactionConfigType0,
    )
    from ..models.sim_agent_update_attributes_model_params_type_0 import (
        SimAgentUpdateAttributesModelParamsType0,
    )
    from ..models.sim_agent_update_attributes_tool_config_type_0 import (
        SimAgentUpdateAttributesToolConfigType0,
    )


T = TypeVar("T", bound="SimAgentUpdateAttributes")


@_attrs_define
class SimAgentUpdateAttributes:
    """
    Attributes:
        name (None | str | Unset):
        personality (None | str | Unset):
        model_name (None | str | Unset):
        model_params (None | SimAgentUpdateAttributesModelParamsType0 | Unset):
        tool_config (None | SimAgentUpdateAttributesToolConfigType0 | Unset):
        memory_compaction_strategy (None | str | Unset):
        memory_compaction_config (None | SimAgentUpdateAttributesMemoryCompactionConfigType0 | Unset):
    """

    name: None | str | Unset = UNSET
    personality: None | str | Unset = UNSET
    model_name: None | str | Unset = UNSET
    model_params: None | SimAgentUpdateAttributesModelParamsType0 | Unset = UNSET
    tool_config: None | SimAgentUpdateAttributesToolConfigType0 | Unset = UNSET
    memory_compaction_strategy: None | str | Unset = UNSET
    memory_compaction_config: (
        None | SimAgentUpdateAttributesMemoryCompactionConfigType0 | Unset
    ) = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.sim_agent_update_attributes_memory_compaction_config_type_0 import (
            SimAgentUpdateAttributesMemoryCompactionConfigType0,
        )
        from ..models.sim_agent_update_attributes_model_params_type_0 import (
            SimAgentUpdateAttributesModelParamsType0,
        )
        from ..models.sim_agent_update_attributes_tool_config_type_0 import (
            SimAgentUpdateAttributesToolConfigType0,
        )

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        personality: None | str | Unset
        if isinstance(self.personality, Unset):
            personality = UNSET
        else:
            personality = self.personality

        model_name: None | str | Unset
        if isinstance(self.model_name, Unset):
            model_name = UNSET
        else:
            model_name = self.model_name

        model_params: dict[str, Any] | None | Unset
        if isinstance(self.model_params, Unset):
            model_params = UNSET
        elif isinstance(self.model_params, SimAgentUpdateAttributesModelParamsType0):
            model_params = self.model_params.to_dict()
        else:
            model_params = self.model_params

        tool_config: dict[str, Any] | None | Unset
        if isinstance(self.tool_config, Unset):
            tool_config = UNSET
        elif isinstance(self.tool_config, SimAgentUpdateAttributesToolConfigType0):
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
            SimAgentUpdateAttributesMemoryCompactionConfigType0,
        ):
            memory_compaction_config = self.memory_compaction_config.to_dict()
        else:
            memory_compaction_config = self.memory_compaction_config

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if personality is not UNSET:
            field_dict["personality"] = personality
        if model_name is not UNSET:
            field_dict["model_name"] = model_name
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
        from ..models.sim_agent_update_attributes_memory_compaction_config_type_0 import (
            SimAgentUpdateAttributesMemoryCompactionConfigType0,
        )
        from ..models.sim_agent_update_attributes_model_params_type_0 import (
            SimAgentUpdateAttributesModelParamsType0,
        )
        from ..models.sim_agent_update_attributes_tool_config_type_0 import (
            SimAgentUpdateAttributesToolConfigType0,
        )

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_personality(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        personality = _parse_personality(d.pop("personality", UNSET))

        def _parse_model_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model_name = _parse_model_name(d.pop("model_name", UNSET))

        def _parse_model_params(
            data: object,
        ) -> None | SimAgentUpdateAttributesModelParamsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                model_params_type_0 = (
                    SimAgentUpdateAttributesModelParamsType0.from_dict(data)
                )

                return model_params_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SimAgentUpdateAttributesModelParamsType0 | Unset, data)

        model_params = _parse_model_params(d.pop("model_params", UNSET))

        def _parse_tool_config(
            data: object,
        ) -> None | SimAgentUpdateAttributesToolConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                tool_config_type_0 = SimAgentUpdateAttributesToolConfigType0.from_dict(
                    data
                )

                return tool_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SimAgentUpdateAttributesToolConfigType0 | Unset, data)

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
        ) -> None | SimAgentUpdateAttributesMemoryCompactionConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                memory_compaction_config_type_0 = (
                    SimAgentUpdateAttributesMemoryCompactionConfigType0.from_dict(data)
                )

                return memory_compaction_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None | SimAgentUpdateAttributesMemoryCompactionConfigType0 | Unset, data
            )

        memory_compaction_config = _parse_memory_compaction_config(
            d.pop("memory_compaction_config", UNSET)
        )

        sim_agent_update_attributes = cls(
            name=name,
            personality=personality,
            model_name=model_name,
            model_params=model_params,
            tool_config=tool_config,
            memory_compaction_strategy=memory_compaction_strategy,
            memory_compaction_config=memory_compaction_config,
        )

        return sim_agent_update_attributes
