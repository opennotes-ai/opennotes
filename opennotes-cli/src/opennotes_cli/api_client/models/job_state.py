from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.error_code import ErrorCode
from ..models.job_status import JobStatus
from ..models.page_kind import PageKind
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.job_state_sections import JobStateSections
    from ..models.sidebar_payload import SidebarPayload


T = TypeVar("T", bound="JobState")


@_attrs_define
class JobState:
    """
    Attributes:
        job_id (UUID):
        url (str):
        status (JobStatus):
        attempt_id (UUID):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        error_code (ErrorCode | None | Unset):
        error_message (None | str | Unset):
        error_host (None | str | Unset): When ErrorCode.UNSUPPORTED_SITE is returned, the host that triggered the
            rejection.
        sections (JobStateSections | Unset):
        sidebar_payload (None | SidebarPayload | Unset):
        sidebar_payload_complete (bool | Unset):  Default: False.
        activity_at (datetime.datetime | None | Unset):
        activity_label (None | str | Unset):
        cached (bool | Unset):  Default: False.
        next_poll_ms (int | Unset):  Default: 1500.
        page_title (None | str | Unset):
        page_kind (None | PageKind | Unset):
        utterance_count (int | Unset):  Default: 0.
    """

    job_id: UUID
    url: str
    status: JobStatus
    attempt_id: UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    error_code: ErrorCode | None | Unset = UNSET
    error_message: None | str | Unset = UNSET
    error_host: None | str | Unset = UNSET
    sections: JobStateSections | Unset = UNSET
    sidebar_payload: None | SidebarPayload | Unset = UNSET
    sidebar_payload_complete: bool | Unset = False
    activity_at: datetime.datetime | None | Unset = UNSET
    activity_label: None | str | Unset = UNSET
    cached: bool | Unset = False
    next_poll_ms: int | Unset = 1500
    page_title: None | str | Unset = UNSET
    page_kind: None | PageKind | Unset = UNSET
    utterance_count: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.sidebar_payload import SidebarPayload

        job_id = str(self.job_id)

        url = self.url

        status = self.status.value

        attempt_id = str(self.attempt_id)

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        error_code: None | str | Unset
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        elif isinstance(self.error_code, ErrorCode):
            error_code = self.error_code.value
        else:
            error_code = self.error_code

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        error_host: None | str | Unset
        if isinstance(self.error_host, Unset):
            error_host = UNSET
        else:
            error_host = self.error_host

        sections: dict[str, Any] | Unset = UNSET
        if not isinstance(self.sections, Unset):
            sections = self.sections.to_dict()

        sidebar_payload: dict[str, Any] | None | Unset
        if isinstance(self.sidebar_payload, Unset):
            sidebar_payload = UNSET
        elif isinstance(self.sidebar_payload, SidebarPayload):
            sidebar_payload = self.sidebar_payload.to_dict()
        else:
            sidebar_payload = self.sidebar_payload

        sidebar_payload_complete = self.sidebar_payload_complete

        activity_at: None | str | Unset
        if isinstance(self.activity_at, Unset):
            activity_at = UNSET
        elif isinstance(self.activity_at, datetime.datetime):
            activity_at = self.activity_at.isoformat()
        else:
            activity_at = self.activity_at

        activity_label: None | str | Unset
        if isinstance(self.activity_label, Unset):
            activity_label = UNSET
        else:
            activity_label = self.activity_label

        cached = self.cached

        next_poll_ms = self.next_poll_ms

        page_title: None | str | Unset
        if isinstance(self.page_title, Unset):
            page_title = UNSET
        else:
            page_title = self.page_title

        page_kind: None | str | Unset
        if isinstance(self.page_kind, Unset):
            page_kind = UNSET
        elif isinstance(self.page_kind, PageKind):
            page_kind = self.page_kind.value
        else:
            page_kind = self.page_kind

        utterance_count = self.utterance_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "job_id": job_id,
                "url": url,
                "status": status,
                "attempt_id": attempt_id,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if error_code is not UNSET:
            field_dict["error_code"] = error_code
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if error_host is not UNSET:
            field_dict["error_host"] = error_host
        if sections is not UNSET:
            field_dict["sections"] = sections
        if sidebar_payload is not UNSET:
            field_dict["sidebar_payload"] = sidebar_payload
        if sidebar_payload_complete is not UNSET:
            field_dict["sidebar_payload_complete"] = sidebar_payload_complete
        if activity_at is not UNSET:
            field_dict["activity_at"] = activity_at
        if activity_label is not UNSET:
            field_dict["activity_label"] = activity_label
        if cached is not UNSET:
            field_dict["cached"] = cached
        if next_poll_ms is not UNSET:
            field_dict["next_poll_ms"] = next_poll_ms
        if page_title is not UNSET:
            field_dict["page_title"] = page_title
        if page_kind is not UNSET:
            field_dict["page_kind"] = page_kind
        if utterance_count is not UNSET:
            field_dict["utterance_count"] = utterance_count

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.job_state_sections import JobStateSections
        from ..models.sidebar_payload import SidebarPayload

        d = dict(src_dict)
        job_id = UUID(d.pop("job_id"))

        url = d.pop("url")

        status = JobStatus(d.pop("status"))

        attempt_id = UUID(d.pop("attempt_id"))

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_error_code(data: object) -> ErrorCode | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                error_code_type_0 = ErrorCode(data)

                return error_code_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ErrorCode | None | Unset, data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        def _parse_error_host(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_host = _parse_error_host(d.pop("error_host", UNSET))

        _sections = d.pop("sections", UNSET)
        sections: JobStateSections | Unset
        if isinstance(_sections, Unset):
            sections = UNSET
        else:
            sections = JobStateSections.from_dict(_sections)

        def _parse_sidebar_payload(data: object) -> None | SidebarPayload | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                sidebar_payload_type_0 = SidebarPayload.from_dict(data)

                return sidebar_payload_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SidebarPayload | Unset, data)

        sidebar_payload = _parse_sidebar_payload(d.pop("sidebar_payload", UNSET))

        sidebar_payload_complete = d.pop("sidebar_payload_complete", UNSET)

        def _parse_activity_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                activity_at_type_0 = isoparse(data)

                return activity_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        activity_at = _parse_activity_at(d.pop("activity_at", UNSET))

        def _parse_activity_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        activity_label = _parse_activity_label(d.pop("activity_label", UNSET))

        cached = d.pop("cached", UNSET)

        next_poll_ms = d.pop("next_poll_ms", UNSET)

        def _parse_page_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        page_title = _parse_page_title(d.pop("page_title", UNSET))

        def _parse_page_kind(data: object) -> None | PageKind | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                page_kind_type_0 = PageKind(data)

                return page_kind_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PageKind | Unset, data)

        page_kind = _parse_page_kind(d.pop("page_kind", UNSET))

        utterance_count = d.pop("utterance_count", UNSET)

        job_state = cls(
            job_id=job_id,
            url=url,
            status=status,
            attempt_id=attempt_id,
            created_at=created_at,
            updated_at=updated_at,
            error_code=error_code,
            error_message=error_message,
            error_host=error_host,
            sections=sections,
            sidebar_payload=sidebar_payload,
            sidebar_payload_complete=sidebar_payload_complete,
            activity_at=activity_at,
            activity_label=activity_label,
            cached=cached,
            next_poll_ms=next_poll_ms,
            page_title=page_title,
            page_kind=page_kind,
            utterance_count=utterance_count,
        )

        job_state.additional_properties = d
        return job_state

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
