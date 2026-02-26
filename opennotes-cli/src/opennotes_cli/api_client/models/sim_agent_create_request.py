from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.sim_agent_create_data import SimAgentCreateData


T = TypeVar("T", bound="SimAgentCreateRequest")


@_attrs_define
class SimAgentCreateRequest:
    """
    Attributes:
        data (SimAgentCreateData):
    """

    data: SimAgentCreateData

    def to_dict(self) -> dict[str, Any]:
        data = self.data.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "data": data,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.sim_agent_create_data import SimAgentCreateData

        d = dict(src_dict)
        data = SimAgentCreateData.from_dict(d.pop("data"))

        sim_agent_create_request = cls(
            data=data,
        )

        return sim_agent_create_request
