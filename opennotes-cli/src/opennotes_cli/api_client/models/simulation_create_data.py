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
    from ..models.simulation_create_attributes import SimulationCreateAttributes


T = TypeVar("T", bound="SimulationCreateData")


@_attrs_define
class SimulationCreateData:
    """
    Attributes:
        type_ (Literal['simulations']): Resource type must be 'simulations'
        attributes (SimulationCreateAttributes):
    """

    type_: Literal["simulations"]
    attributes: SimulationCreateAttributes

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        attributes = self.attributes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "attributes": attributes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.simulation_create_attributes import SimulationCreateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["simulations"], d.pop("type"))
        if type_ != "simulations":
            raise ValueError(f"type must match const 'simulations', got '{type_}'")

        attributes = SimulationCreateAttributes.from_dict(d.pop("attributes"))

        simulation_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return simulation_create_data
