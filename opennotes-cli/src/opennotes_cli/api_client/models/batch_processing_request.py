from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="BatchProcessingRequest")


@_attrs_define
class BatchProcessingRequest:
    """Request parameters for batch processing operations without rate limiting (e.g., promote).

    Attributes:
        batch_size (int | Unset): Maximum number of candidates to process in this batch Default: 1000.
        dry_run (bool | Unset): Count candidates only, do not perform operation Default: False.
    """

    batch_size: int | Unset = 1000
    dry_run: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        batch_size = self.batch_size

        dry_run = self.dry_run

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if batch_size is not UNSET:
            field_dict["batch_size"] = batch_size
        if dry_run is not UNSET:
            field_dict["dry_run"] = dry_run

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        batch_size = d.pop("batch_size", UNSET)

        dry_run = d.pop("dry_run", UNSET)

        batch_processing_request = cls(
            batch_size=batch_size,
            dry_run=dry_run,
        )

        return batch_processing_request
