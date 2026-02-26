from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="MonitoredChannelAttributes")


@_attrs_define
class MonitoredChannelAttributes:
    """Monitored channel attributes for JSON:API resource.

    Attributes:
        community_server_id (str):
        channel_id (str):
        enabled (bool):
        similarity_threshold (float):
        dataset_tags (list[str]):
        name (None | str | Unset):
        previously_seen_autopublish_threshold (float | None | Unset):
        previously_seen_autorequest_threshold (float | None | Unset):
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
        updated_by (None | str | Unset):
    """

    community_server_id: str
    channel_id: str
    enabled: bool
    similarity_threshold: float
    dataset_tags: list[str]
    name: None | str | Unset = UNSET
    previously_seen_autopublish_threshold: float | None | Unset = UNSET
    previously_seen_autorequest_threshold: float | None | Unset = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    updated_by: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        community_server_id = self.community_server_id

        channel_id = self.channel_id

        enabled = self.enabled

        similarity_threshold = self.similarity_threshold

        dataset_tags = self.dataset_tags

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

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

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        updated_by: None | str | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        else:
            updated_by = self.updated_by

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "community_server_id": community_server_id,
                "channel_id": channel_id,
                "enabled": enabled,
                "similarity_threshold": similarity_threshold,
                "dataset_tags": dataset_tags,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name
        if previously_seen_autopublish_threshold is not UNSET:
            field_dict["previously_seen_autopublish_threshold"] = (
                previously_seen_autopublish_threshold
            )
        if previously_seen_autorequest_threshold is not UNSET:
            field_dict["previously_seen_autorequest_threshold"] = (
                previously_seen_autorequest_threshold
            )
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        community_server_id = d.pop("community_server_id")

        channel_id = d.pop("channel_id")

        enabled = d.pop("enabled")

        similarity_threshold = d.pop("similarity_threshold")

        dataset_tags = cast(list[str], d.pop("dataset_tags"))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

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

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        def _parse_updated_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        monitored_channel_attributes = cls(
            community_server_id=community_server_id,
            channel_id=channel_id,
            enabled=enabled,
            similarity_threshold=similarity_threshold,
            dataset_tags=dataset_tags,
            name=name,
            previously_seen_autopublish_threshold=previously_seen_autopublish_threshold,
            previously_seen_autorequest_threshold=previously_seen_autorequest_threshold,
            created_at=created_at,
            updated_at=updated_at,
            updated_by=updated_by,
        )

        monitored_channel_attributes.additional_properties = d
        return monitored_channel_attributes

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
