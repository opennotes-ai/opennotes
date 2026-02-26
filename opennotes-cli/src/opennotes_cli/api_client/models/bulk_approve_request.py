from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.candidate_status import CandidateStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="BulkApproveRequest")


@_attrs_define
class BulkApproveRequest:
    """Request body for bulk approval from predicted_ratings.

    Note: This is not wrapped in JSON:API data envelope since it's an action
    endpoint that accepts filter parameters, not a resource creation.

        Attributes:
            threshold (float | Unset): Predictions >= threshold get approved Default: 1.0.
            auto_promote (bool | Unset): Whether to promote approved candidates that are ready Default: False.
            status (CandidateStatus | None | Unset): Filter by candidate status
            dataset_name (None | str | Unset): Filter by dataset name (exact match)
            dataset_tags (list[str] | None | Unset): Filter by dataset tags (array overlap)
            has_content (bool | None | Unset): Filter by whether candidate has content
            published_date_from (datetime.datetime | None | Unset): Filter by published_date >= this value
            published_date_to (datetime.datetime | None | Unset): Filter by published_date <= this value
            limit (int | Unset): Maximum number of candidates to approve (default 200) Default: 200.
    """

    threshold: float | Unset = 1.0
    auto_promote: bool | Unset = False
    status: CandidateStatus | None | Unset = UNSET
    dataset_name: None | str | Unset = UNSET
    dataset_tags: list[str] | None | Unset = UNSET
    has_content: bool | None | Unset = UNSET
    published_date_from: datetime.datetime | None | Unset = UNSET
    published_date_to: datetime.datetime | None | Unset = UNSET
    limit: int | Unset = 200

    def to_dict(self) -> dict[str, Any]:
        threshold = self.threshold

        auto_promote = self.auto_promote

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        elif isinstance(self.status, CandidateStatus):
            status = self.status.value
        else:
            status = self.status

        dataset_name: None | str | Unset
        if isinstance(self.dataset_name, Unset):
            dataset_name = UNSET
        else:
            dataset_name = self.dataset_name

        dataset_tags: list[str] | None | Unset
        if isinstance(self.dataset_tags, Unset):
            dataset_tags = UNSET
        elif isinstance(self.dataset_tags, list):
            dataset_tags = self.dataset_tags

        else:
            dataset_tags = self.dataset_tags

        has_content: bool | None | Unset
        if isinstance(self.has_content, Unset):
            has_content = UNSET
        else:
            has_content = self.has_content

        published_date_from: None | str | Unset
        if isinstance(self.published_date_from, Unset):
            published_date_from = UNSET
        elif isinstance(self.published_date_from, datetime.datetime):
            published_date_from = self.published_date_from.isoformat()
        else:
            published_date_from = self.published_date_from

        published_date_to: None | str | Unset
        if isinstance(self.published_date_to, Unset):
            published_date_to = UNSET
        elif isinstance(self.published_date_to, datetime.datetime):
            published_date_to = self.published_date_to.isoformat()
        else:
            published_date_to = self.published_date_to

        limit = self.limit

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if threshold is not UNSET:
            field_dict["threshold"] = threshold
        if auto_promote is not UNSET:
            field_dict["auto_promote"] = auto_promote
        if status is not UNSET:
            field_dict["status"] = status
        if dataset_name is not UNSET:
            field_dict["dataset_name"] = dataset_name
        if dataset_tags is not UNSET:
            field_dict["dataset_tags"] = dataset_tags
        if has_content is not UNSET:
            field_dict["has_content"] = has_content
        if published_date_from is not UNSET:
            field_dict["published_date_from"] = published_date_from
        if published_date_to is not UNSET:
            field_dict["published_date_to"] = published_date_to
        if limit is not UNSET:
            field_dict["limit"] = limit

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        threshold = d.pop("threshold", UNSET)

        auto_promote = d.pop("auto_promote", UNSET)

        def _parse_status(data: object) -> CandidateStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_type_0 = CandidateStatus(data)

                return status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CandidateStatus | None | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        def _parse_dataset_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dataset_name = _parse_dataset_name(d.pop("dataset_name", UNSET))

        def _parse_dataset_tags(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                dataset_tags_type_0 = cast(list[str], data)

                return dataset_tags_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        dataset_tags = _parse_dataset_tags(d.pop("dataset_tags", UNSET))

        def _parse_has_content(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        has_content = _parse_has_content(d.pop("has_content", UNSET))

        def _parse_published_date_from(
            data: object,
        ) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                published_date_from_type_0 = isoparse(data)

                return published_date_from_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        published_date_from = _parse_published_date_from(
            d.pop("published_date_from", UNSET)
        )

        def _parse_published_date_to(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                published_date_to_type_0 = isoparse(data)

                return published_date_to_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        published_date_to = _parse_published_date_to(d.pop("published_date_to", UNSET))

        limit = d.pop("limit", UNSET)

        bulk_approve_request = cls(
            threshold=threshold,
            auto_promote=auto_promote,
            status=status,
            dataset_name=dataset_name,
            dataset_tags=dataset_tags,
            has_content=has_content,
            published_date_from=published_date_from,
            published_date_to=published_date_to,
            limit=limit,
        )

        return bulk_approve_request
