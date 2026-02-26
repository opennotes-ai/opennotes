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
    from ..models.orchestrator_create_attributes import OrchestratorCreateAttributes


T = TypeVar("T", bound="OrchestratorCreateData")


@_attrs_define
class OrchestratorCreateData:
    """
    Attributes:
        type_ (Literal['simulation-orchestrators']): Resource type must be 'simulation-orchestrators'
        attributes (OrchestratorCreateAttributes):
    """

    type_: Literal["simulation-orchestrators"]
    attributes: OrchestratorCreateAttributes

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
        from ..models.orchestrator_create_attributes import OrchestratorCreateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["simulation-orchestrators"], d.pop("type"))
        if type_ != "simulation-orchestrators":
            raise ValueError(
                f"type must match const 'simulation-orchestrators', got '{type_}'"
            )

        attributes = OrchestratorCreateAttributes.from_dict(d.pop("attributes"))

        orchestrator_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return orchestrator_create_data
