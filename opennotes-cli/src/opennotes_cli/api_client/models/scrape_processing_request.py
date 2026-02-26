from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ScrapeProcessingRequest")


@_attrs_define
class ScrapeProcessingRequest:
    """Request parameters for scraping operations with rate limiting support.

    Attributes:
        batch_size (int | Unset): Maximum number of candidates to process in this batch Default: 1000.
        dry_run (bool | Unset): Count candidates only, do not perform operation Default: False.
        base_delay (float | Unset): Minimum delay in seconds between requests to the same domain Default: 1.0.
    """

    batch_size: int | Unset = 1000
    dry_run: bool | Unset = False
    base_delay: float | Unset = 1.0

    def to_dict(self) -> dict[str, Any]:
        batch_size = self.batch_size

        dry_run = self.dry_run

        base_delay = self.base_delay

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if batch_size is not UNSET:
            field_dict["batch_size"] = batch_size
        if dry_run is not UNSET:
            field_dict["dry_run"] = dry_run
        if base_delay is not UNSET:
            field_dict["base_delay"] = base_delay

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        batch_size = d.pop("batch_size", UNSET)

        dry_run = d.pop("dry_run", UNSET)

        base_delay = d.pop("base_delay", UNSET)

        scrape_processing_request = cls(
            batch_size=batch_size,
            dry_run=dry_run,
            base_delay=base_delay,
        )

        return scrape_processing_request
