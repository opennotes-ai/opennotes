from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="SimulationCreateAttributes")


@_attrs_define
class SimulationCreateAttributes:
    """
    Attributes:
        orchestrator_id (UUID):
        community_server_id (UUID):
    """

    orchestrator_id: UUID
    community_server_id: UUID

    def to_dict(self) -> dict[str, Any]:
        orchestrator_id = str(self.orchestrator_id)

        community_server_id = str(self.community_server_id)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "orchestrator_id": orchestrator_id,
                "community_server_id": community_server_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        orchestrator_id = UUID(d.pop("orchestrator_id"))

        community_server_id = UUID(d.pop("community_server_id"))

        simulation_create_attributes = cls(
            orchestrator_id=orchestrator_id,
            community_server_id=community_server_id,
        )

        return simulation_create_attributes
