from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="MonitoredChannelCreateAttributes")


@_attrs_define
class MonitoredChannelCreateAttributes:
    """Attributes for creating a monitored channel via JSON:API.

    Attributes:
        community_server_id (str): Discord server/guild ID (platform ID)
        channel_id (str): Discord channel ID
        name (None | str | Unset): Human-readable channel name
        enabled (bool | Unset): Whether monitoring is active Default: True.
        similarity_threshold (float | Unset): Minimum similarity score (0.0-1.0) for matches
        dataset_tags (list[str] | Unset): Dataset tags to check against
        previously_seen_autopublish_threshold (float | None | Unset): Per-channel override for auto-publish threshold
        previously_seen_autorequest_threshold (float | None | Unset): Per-channel override for auto-request threshold
        updated_by (None | str | Unset): Discord user ID of admin creating config
    """

    community_server_id: str
    channel_id: str
    name: None | str | Unset = UNSET
    enabled: bool | Unset = True
    similarity_threshold: float | Unset = UNSET
    dataset_tags: list[str] | Unset = UNSET
    previously_seen_autopublish_threshold: float | None | Unset = UNSET
    previously_seen_autorequest_threshold: float | None | Unset = UNSET
    updated_by: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        community_server_id = self.community_server_id

        channel_id = self.channel_id

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        enabled = self.enabled

        similarity_threshold = self.similarity_threshold

        dataset_tags: list[str] | Unset = UNSET
        if not isinstance(self.dataset_tags, Unset):
            dataset_tags = self.dataset_tags

        previously_seen_autopublish_threshold: float | None | Unset
        if isinstance(self.previously_seen_autopublish_threshold, Unset):
            previously_seen_autopublish_threshold = UNSET
        else:
            previously_seen_autopublish_threshold = (
                self.previously_seen_autopublish_threshold
            )

        previously_seen_autorequest_threshold: float | None | Unset
        if isinstance(self.previously_seen_autorequest_threshold, Unset):
            previously_seen_autorequest_threshold = UNSET
        else:
            previously_seen_autorequest_threshold = (
                self.previously_seen_autorequest_threshold
            )

        updated_by: None | str | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        else:
            updated_by = self.updated_by

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "community_server_id": community_server_id,
                "channel_id": channel_id,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if similarity_threshold is not UNSET:
            field_dict["similarity_threshold"] = similarity_threshold
        if dataset_tags is not UNSET:
            field_dict["dataset_tags"] = dataset_tags
        if previously_seen_autopublish_threshold is not UNSET:
            field_dict["previously_seen_autopublish_threshold"] = (
                previously_seen_autopublish_threshold
            )
        if previously_seen_autorequest_threshold is not UNSET:
            field_dict["previously_seen_autorequest_threshold"] = (
                previously_seen_autorequest_threshold
            )
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        community_server_id = d.pop("community_server_id")

        channel_id = d.pop("channel_id")

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        enabled = d.pop("enabled", UNSET)

        similarity_threshold = d.pop("similarity_threshold", UNSET)

        dataset_tags = cast(list[str], d.pop("dataset_tags", UNSET))

        def _parse_previously_seen_autopublish_threshold(
            data: object,
        ) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        previously_seen_autopublish_threshold = (
            _parse_previously_seen_autopublish_threshold(
                d.pop("previously_seen_autopublish_threshold", UNSET)
            )
        )

        def _parse_previously_seen_autorequest_threshold(
            data: object,
        ) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        previously_seen_autorequest_threshold = (
            _parse_previously_seen_autorequest_threshold(
                d.pop("previously_seen_autorequest_threshold", UNSET)
            )
        )

        def _parse_updated_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        monitored_channel_create_attributes = cls(
            community_server_id=community_server_id,
            channel_id=channel_id,
            name=name,
            enabled=enabled,
            similarity_threshold=similarity_threshold,
            dataset_tags=dataset_tags,
            previously_seen_autopublish_threshold=previously_seen_autopublish_threshold,
            previously_seen_autorequest_threshold=previously_seen_autorequest_threshold,
            updated_by=updated_by,
        )

        return monitored_channel_create_attributes
