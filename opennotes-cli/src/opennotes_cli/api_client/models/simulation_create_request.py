from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.simulation_create_data import SimulationCreateData


T = TypeVar("T", bound="SimulationCreateRequest")


@_attrs_define
class SimulationCreateRequest:
    """
    Attributes:
        data (SimulationCreateData):
    """

    data: SimulationCreateData

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
        from ..models.simulation_create_data import SimulationCreateData

        d = dict(src_dict)
        data = SimulationCreateData.from_dict(d.pop("data"))

        simulation_create_request = cls(
            data=data,
        )

        return simulation_create_request
