from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="NotePublisherConfigCreateAttributes")


@_attrs_define
class NotePublisherConfigCreateAttributes:
    """Attributes for creating a note publisher config via JSON:API.

    Attributes:
        community_server_id (str): Discord server/guild ID (platform ID)
        channel_id (None | str | Unset): Discord channel ID (None for server-wide)
        enabled (bool | Unset): Whether auto-publishing is enabled Default: True.
        threshold (float | None | Unset): Score threshold for auto-publishing (0.0-1.0)
        updated_by (None | str | Unset): Discord user ID of admin
    """

    community_server_id: str
    channel_id: None | str | Unset = UNSET
    enabled: bool | Unset = True
    threshold: float | None | Unset = UNSET
    updated_by: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        community_server_id = self.community_server_id

        channel_id: None | str | Unset
        if isinstance(self.channel_id, Unset):
            channel_id = UNSET
        else:
            channel_id = self.channel_id

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

        field_dict.update(
            {
                "community_server_id": community_server_id,
            }
        )
        if channel_id is not UNSET:
            field_dict["channel_id"] = channel_id
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
        community_server_id = d.pop("community_server_id")

        def _parse_channel_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        channel_id = _parse_channel_id(d.pop("channel_id", UNSET))

        enabled = d.pop("enabled", UNSET)

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

        note_publisher_config_create_attributes = cls(
            community_server_id=community_server_id,
            channel_id=channel_id,
            enabled=enabled,
            threshold=threshold,
            updated_by=updated_by,
        )

        return note_publisher_config_create_attributes
