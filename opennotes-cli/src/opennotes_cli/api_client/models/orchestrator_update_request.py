from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.orchestrator_update_data import OrchestratorUpdateData


T = TypeVar("T", bound="OrchestratorUpdateRequest")


@_attrs_define
class OrchestratorUpdateRequest:
    """
    Attributes:
        data (OrchestratorUpdateData):
    """

    data: OrchestratorUpdateData

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
        from ..models.orchestrator_update_data import OrchestratorUpdateData

        d = dict(src_dict)
        data = OrchestratorUpdateData.from_dict(d.pop("data"))

        orchestrator_update_request = cls(
            data=data,
        )

        return orchestrator_update_request
