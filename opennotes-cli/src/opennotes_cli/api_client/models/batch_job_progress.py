from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BatchJobProgress")


@_attrs_define
class BatchJobProgress:
    """Real-time progress information from Redis cache.

    Attributes:
        job_id (UUID): Job identifier
        processed_count (int | Unset): Items processed so far Default: 0.
        error_count (int | Unset): Errors encountered Default: 0.
        current_item (None | str | Unset): Currently processing item
        rate (float | Unset): Processing rate (items/second) Default: 0.0.
        eta_seconds (float | None | Unset): Estimated time to completion
    """

    job_id: UUID
    processed_count: int | Unset = 0
    error_count: int | Unset = 0
    current_item: None | str | Unset = UNSET
    rate: float | Unset = 0.0
    eta_seconds: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        job_id = str(self.job_id)

        processed_count = self.processed_count

        error_count = self.error_count

        current_item: None | str | Unset
        if isinstance(self.current_item, Unset):
            current_item = UNSET
        else:
            current_item = self.current_item

        rate = self.rate

        eta_seconds: float | None | Unset
        if isinstance(self.eta_seconds, Unset):
            eta_seconds = UNSET
        else:
            eta_seconds = self.eta_seconds

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "job_id": job_id,
            }
        )
        if processed_count is not UNSET:
            field_dict["processed_count"] = processed_count
        if error_count is not UNSET:
            field_dict["error_count"] = error_count
        if current_item is not UNSET:
            field_dict["current_item"] = current_item
        if rate is not UNSET:
            field_dict["rate"] = rate
        if eta_seconds is not UNSET:
            field_dict["eta_seconds"] = eta_seconds

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        job_id = UUID(d.pop("job_id"))

        processed_count = d.pop("processed_count", UNSET)

        error_count = d.pop("error_count", UNSET)

        def _parse_current_item(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        current_item = _parse_current_item(d.pop("current_item", UNSET))

        rate = d.pop("rate", UNSET)

        def _parse_eta_seconds(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        eta_seconds = _parse_eta_seconds(d.pop("eta_seconds", UNSET))

        batch_job_progress = cls(
            job_id=job_id,
            processed_count=processed_count,
            error_count=error_count,
            current_item=current_item,
            rate=rate,
            eta_seconds=eta_seconds,
        )

        batch_job_progress.additional_properties = d
        return batch_job_progress

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
