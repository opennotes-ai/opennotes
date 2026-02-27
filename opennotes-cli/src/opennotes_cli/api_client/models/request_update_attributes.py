from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..models.request_status import RequestStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="RequestUpdateAttributes")


@_attrs_define
class RequestUpdateAttributes:
    """Attributes for updating a request via JSON:API.

    Attributes:
        status (None | RequestStatus | Unset): Updated request status
        note_id (None | Unset | UUID): Associated note ID
    """

    status: None | RequestStatus | Unset = UNSET
    note_id: None | Unset | UUID = UNSET

    def to_dict(self) -> dict[str, Any]:
        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        elif isinstance(self.status, RequestStatus):
            status = self.status.value
        else:
            status = self.status

        note_id: None | str | Unset
        if isinstance(self.note_id, Unset):
            note_id = UNSET
        elif isinstance(self.note_id, UUID):
            note_id = str(self.note_id)
        else:
            note_id = self.note_id

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if status is not UNSET:
            field_dict["status"] = status
        if note_id is not UNSET:
            field_dict["note_id"] = note_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_status(data: object) -> None | RequestStatus | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_type_0 = RequestStatus(data)

                return status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RequestStatus | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        def _parse_note_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                note_id_type_0 = UUID(data)

                return note_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        note_id = _parse_note_id(d.pop("note_id", UNSET))

        request_update_attributes = cls(
            status=status,
            note_id=note_id,
        )

        return request_update_attributes
