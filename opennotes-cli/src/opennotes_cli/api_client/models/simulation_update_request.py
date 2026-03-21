from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.simulation_update_data import SimulationUpdateData


T = TypeVar("T", bound="SimulationUpdateRequest")


@_attrs_define
class SimulationUpdateRequest:
    """
    Attributes:
        data (SimulationUpdateData):
    """

    data: SimulationUpdateData

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
        from ..models.simulation_update_data import SimulationUpdateData

        d = dict(src_dict)
        data = SimulationUpdateData.from_dict(d.pop("data"))

        simulation_update_request = cls(
            data=data,
        )

        return simulation_update_request
