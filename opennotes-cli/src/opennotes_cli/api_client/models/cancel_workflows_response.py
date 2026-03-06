from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CancelWorkflowsResponse")


@_attrs_define
class CancelWorkflowsResponse:
    """
    Attributes:
        simulation_id (str):
        dry_run (bool):
        workflow_ids (list[str]):
        total (int):
        cancelled (int):
        generation (int | None | Unset):
        errors (list[str] | Unset):
    """

    simulation_id: str
    dry_run: bool
    workflow_ids: list[str]
    total: int
    cancelled: int
    generation: int | None | Unset = UNSET
    errors: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        simulation_id = self.simulation_id

        dry_run = self.dry_run

        workflow_ids = self.workflow_ids

        total = self.total

        cancelled = self.cancelled

        generation: int | None | Unset
        if isinstance(self.generation, Unset):
            generation = UNSET
        else:
            generation = self.generation

        errors: list[str] | Unset = UNSET
        if not isinstance(self.errors, Unset):
            errors = self.errors

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "simulation_id": simulation_id,
                "dry_run": dry_run,
                "workflow_ids": workflow_ids,
                "total": total,
                "cancelled": cancelled,
            }
        )
        if generation is not UNSET:
            field_dict["generation"] = generation
        if errors is not UNSET:
            field_dict["errors"] = errors

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        simulation_id = d.pop("simulation_id")

        dry_run = d.pop("dry_run")

        workflow_ids = cast(list[str], d.pop("workflow_ids"))

        total = d.pop("total")

        cancelled = d.pop("cancelled")

        def _parse_generation(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        generation = _parse_generation(d.pop("generation", UNSET))

        errors = cast(list[str], d.pop("errors", UNSET))

        cancel_workflows_response = cls(
            simulation_id=simulation_id,
            dry_run=dry_run,
            workflow_ids=workflow_ids,
            total=total,
            cancelled=cancelled,
            generation=generation,
            errors=errors,
        )

        cancel_workflows_response.additional_properties = d
        return cancel_workflows_response

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
