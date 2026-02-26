from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ImportFactCheckBureauRequest")


@_attrs_define
class ImportFactCheckBureauRequest:
    """Request parameters for fact-check bureau import.

    Attributes:
        batch_size (int | Unset): Batch size for import operations Default: 1000.
        dry_run (bool | Unset): Validate only, do not insert into database Default: False.
        enqueue_scrapes (bool | Unset): Enqueue scrape tasks for pending candidates after import completes Default:
            False.
    """

    batch_size: int | Unset = 1000
    dry_run: bool | Unset = False
    enqueue_scrapes: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        batch_size = self.batch_size

        dry_run = self.dry_run

        enqueue_scrapes = self.enqueue_scrapes

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if batch_size is not UNSET:
            field_dict["batch_size"] = batch_size
        if dry_run is not UNSET:
            field_dict["dry_run"] = dry_run
        if enqueue_scrapes is not UNSET:
            field_dict["enqueue_scrapes"] = enqueue_scrapes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        batch_size = d.pop("batch_size", UNSET)

        dry_run = d.pop("dry_run", UNSET)

        enqueue_scrapes = d.pop("enqueue_scrapes", UNSET)

        import_fact_check_bureau_request = cls(
            batch_size=batch_size,
            dry_run=dry_run,
            enqueue_scrapes=enqueue_scrapes,
        )

        return import_fact_check_bureau_request
