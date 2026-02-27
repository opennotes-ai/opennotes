from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.batch_job_status import BatchJobStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.batch_job_response_error_summary_type_0 import (
        BatchJobResponseErrorSummaryType0,
    )
    from ..models.batch_job_response_metadata import BatchJobResponseMetadata


T = TypeVar("T", bound="BatchJobResponse")


@_attrs_define
class BatchJobResponse:
    """Response schema for batch job with full details.

    Attributes:
        job_type (str): Type of batch job (e.g., 'fact_check_import')
        id (UUID): Unique job identifier
        status (BatchJobStatus): Status states for a batch job.
        created_at (datetime.datetime): When the job was created
        total_tasks (int | Unset): Total tasks to process Default: 0.
        completed_tasks (int | Unset): Tasks completed successfully Default: 0.
        failed_tasks (int | Unset): Tasks that failed Default: 0.
        metadata (BatchJobResponseMetadata | Unset): Job-specific metadata
        error_summary (BatchJobResponseErrorSummaryType0 | None | Unset): Summary of errors if any
        workflow_id (None | str | Unset): DBOS workflow ID for linking batch job to workflow execution
        started_at (datetime.datetime | None | Unset): When the job started processing
        completed_at (datetime.datetime | None | Unset): When the job finished
        updated_at (datetime.datetime | None | Unset): When the job was last updated
    """

    job_type: str
    id: UUID
    status: BatchJobStatus
    created_at: datetime.datetime
    total_tasks: int | Unset = 0
    completed_tasks: int | Unset = 0
    failed_tasks: int | Unset = 0
    metadata: BatchJobResponseMetadata | Unset = UNSET
    error_summary: BatchJobResponseErrorSummaryType0 | None | Unset = UNSET
    workflow_id: None | str | Unset = UNSET
    started_at: datetime.datetime | None | Unset = UNSET
    completed_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.batch_job_response_error_summary_type_0 import (
            BatchJobResponseErrorSummaryType0,
        )

        job_type = self.job_type

        id = str(self.id)

        status = self.status.value

        created_at = self.created_at.isoformat()

        total_tasks = self.total_tasks

        completed_tasks = self.completed_tasks

        failed_tasks = self.failed_tasks

        metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        error_summary: dict[str, Any] | None | Unset
        if isinstance(self.error_summary, Unset):
            error_summary = UNSET
        elif isinstance(self.error_summary, BatchJobResponseErrorSummaryType0):
            error_summary = self.error_summary.to_dict()
        else:
            error_summary = self.error_summary

        workflow_id: None | str | Unset
        if isinstance(self.workflow_id, Unset):
            workflow_id = UNSET
        else:
            workflow_id = self.workflow_id

        started_at: None | str | Unset
        if isinstance(self.started_at, Unset):
            started_at = UNSET
        elif isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        completed_at: None | str | Unset
        if isinstance(self.completed_at, Unset):
            completed_at = UNSET
        elif isinstance(self.completed_at, datetime.datetime):
            completed_at = self.completed_at.isoformat()
        else:
            completed_at = self.completed_at

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "job_type": job_type,
                "id": id,
                "status": status,
                "created_at": created_at,
            }
        )
        if total_tasks is not UNSET:
            field_dict["total_tasks"] = total_tasks
        if completed_tasks is not UNSET:
            field_dict["completed_tasks"] = completed_tasks
        if failed_tasks is not UNSET:
            field_dict["failed_tasks"] = failed_tasks
        if metadata is not UNSET:
            field_dict["metadata_"] = metadata
        if error_summary is not UNSET:
            field_dict["error_summary"] = error_summary
        if workflow_id is not UNSET:
            field_dict["workflow_id"] = workflow_id
        if started_at is not UNSET:
            field_dict["started_at"] = started_at
        if completed_at is not UNSET:
            field_dict["completed_at"] = completed_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.batch_job_response_error_summary_type_0 import (
            BatchJobResponseErrorSummaryType0,
        )
        from ..models.batch_job_response_metadata import BatchJobResponseMetadata

        d = dict(src_dict)
        job_type = d.pop("job_type")

        id = UUID(d.pop("id"))

        status = BatchJobStatus(d.pop("status"))

        created_at = isoparse(d.pop("created_at"))

        total_tasks = d.pop("total_tasks", UNSET)

        completed_tasks = d.pop("completed_tasks", UNSET)

        failed_tasks = d.pop("failed_tasks", UNSET)

        _metadata = d.pop("metadata_", UNSET)
        metadata: BatchJobResponseMetadata | Unset
        if isinstance(_metadata, Unset):
            metadata = UNSET
        else:
            metadata = BatchJobResponseMetadata.from_dict(_metadata)

        def _parse_error_summary(
            data: object,
        ) -> BatchJobResponseErrorSummaryType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                error_summary_type_0 = BatchJobResponseErrorSummaryType0.from_dict(data)

                return error_summary_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BatchJobResponseErrorSummaryType0 | None | Unset, data)

        error_summary = _parse_error_summary(d.pop("error_summary", UNSET))

        def _parse_workflow_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        workflow_id = _parse_workflow_id(d.pop("workflow_id", UNSET))

        def _parse_started_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                started_at_type_0 = isoparse(data)

                return started_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        started_at = _parse_started_at(d.pop("started_at", UNSET))

        def _parse_completed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                completed_at_type_0 = isoparse(data)

                return completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        batch_job_response = cls(
            job_type=job_type,
            id=id,
            status=status,
            created_at=created_at,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            metadata=metadata,
            error_summary=error_summary,
            workflow_id=workflow_id,
            started_at=started_at,
            completed_at=completed_at,
            updated_at=updated_at,
        )

        batch_job_response.additional_properties = d
        return batch_job_response

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
