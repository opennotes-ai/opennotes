from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.batch_job_create_metadata import BatchJobCreateMetadata


T = TypeVar("T", bound="BatchJobCreate")


@_attrs_define
class BatchJobCreate:
    """Schema for creating a new batch job.

    Attributes:
        job_type (str): Type of batch job (e.g., 'fact_check_import')
        total_tasks (int | Unset): Total number of tasks to process Default: 0.
        metadata (BatchJobCreateMetadata | Unset): Job-specific metadata (e.g., source file, options)
        workflow_id (None | str | Unset): DBOS workflow ID for linking batch job to workflow execution
    """

    job_type: str
    total_tasks: int | Unset = 0
    metadata: BatchJobCreateMetadata | Unset = UNSET
    workflow_id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        job_type = self.job_type

        total_tasks = self.total_tasks

        metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        workflow_id: None | str | Unset
        if isinstance(self.workflow_id, Unset):
            workflow_id = UNSET
        else:
            workflow_id = self.workflow_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "job_type": job_type,
            }
        )
        if total_tasks is not UNSET:
            field_dict["total_tasks"] = total_tasks
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if workflow_id is not UNSET:
            field_dict["workflow_id"] = workflow_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.batch_job_create_metadata import BatchJobCreateMetadata

        d = dict(src_dict)
        job_type = d.pop("job_type")

        total_tasks = d.pop("total_tasks", UNSET)

        _metadata = d.pop("metadata", UNSET)
        metadata: BatchJobCreateMetadata | Unset
        if isinstance(_metadata, Unset):
            metadata = UNSET
        else:
            metadata = BatchJobCreateMetadata.from_dict(_metadata)

        def _parse_workflow_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        workflow_id = _parse_workflow_id(d.pop("workflow_id", UNSET))

        batch_job_create = cls(
            job_type=job_type,
            total_tasks=total_tasks,
            metadata=metadata,
            workflow_id=workflow_id,
        )

        return batch_job_create
