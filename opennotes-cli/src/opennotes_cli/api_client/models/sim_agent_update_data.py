from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.sim_agent_update_attributes import SimAgentUpdateAttributes


T = TypeVar("T", bound="SimAgentUpdateData")


@_attrs_define
class SimAgentUpdateData:
    """
    Attributes:
        type_ (Literal['sim-agents']): Resource type must be 'sim-agents'
        id (str): SimAgent ID
        attributes (SimAgentUpdateAttributes):
    """

    type_: Literal["sim-agents"]
    id: str
    attributes: SimAgentUpdateAttributes

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        id = self.id

        attributes = self.attributes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "id": id,
                "attributes": attributes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.sim_agent_update_attributes import SimAgentUpdateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["sim-agents"], d.pop("type"))
        if type_ != "sim-agents":
            raise ValueError(f"type must match const 'sim-agents', got '{type_}'")

        id = d.pop("id")

        attributes = SimAgentUpdateAttributes.from_dict(d.pop("attributes"))

        sim_agent_update_data = cls(
            type_=type_,
            id=id,
            attributes=attributes,
        )

        return sim_agent_update_data
