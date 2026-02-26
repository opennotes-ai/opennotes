from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="NotePublisherConfigUpdateAttributes")


@_attrs_define
class NotePublisherConfigUpdateAttributes:
    """Attributes for updating a note publisher config via JSON:API.

    Attributes:
        enabled (bool | None | Unset): Whether auto-publishing is enabled
        threshold (float | None | Unset): Score threshold for auto-publishing (0.0-1.0)
        updated_by (None | str | Unset): Discord user ID of admin
    """

    enabled: bool | None | Unset = UNSET
    threshold: float | None | Unset = UNSET
    updated_by: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        threshold: float | None | Unset
        if isinstance(self.threshold, Unset):
            threshold = UNSET
        else:
            threshold = self.threshold

        updated_by: None | str | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        else:
            updated_by = self.updated_by

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if threshold is not UNSET:
            field_dict["threshold"] = threshold
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))

        def _parse_threshold(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        threshold = _parse_threshold(d.pop("threshold", UNSET))

        def _parse_updated_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        note_publisher_config_update_attributes = cls(
            enabled=enabled,
            threshold=threshold,
            updated_by=updated_by,
        )

        return note_publisher_config_update_attributes
