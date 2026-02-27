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
    from ..models.orchestrator_update_attributes import OrchestratorUpdateAttributes


T = TypeVar("T", bound="OrchestratorUpdateData")


@_attrs_define
class OrchestratorUpdateData:
    """
    Attributes:
        type_ (Literal['simulation-orchestrators']): Resource type must be 'simulation-orchestrators'
        id (str): Orchestrator ID
        attributes (OrchestratorUpdateAttributes):
    """

    type_: Literal["simulation-orchestrators"]
    id: str
    attributes: OrchestratorUpdateAttributes

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
        from ..models.orchestrator_update_attributes import OrchestratorUpdateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["simulation-orchestrators"], d.pop("type"))
        if type_ != "simulation-orchestrators":
            raise ValueError(
                f"type must match const 'simulation-orchestrators', got '{type_}'"
            )

        id = d.pop("id")

        attributes = OrchestratorUpdateAttributes.from_dict(d.pop("attributes"))

        orchestrator_update_data = cls(
            type_=type_,
            id=id,
            attributes=attributes,
        )

        return orchestrator_update_data
