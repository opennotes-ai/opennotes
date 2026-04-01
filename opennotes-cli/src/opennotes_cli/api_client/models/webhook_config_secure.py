from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="WebhookConfigSecure")


@_attrs_define
class WebhookConfigSecure:
    """
    Attributes:
        id (UUID):
        url (str):
        community_server_id (UUID):
        active (bool):
        secret (str):
        channel_id (None | str | Unset):
        events (list[str] | None | Unset):
    """

    id: UUID
    url: str
    community_server_id: UUID
    active: bool
    secret: str
    channel_id: None | str | Unset = UNSET
    events: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        url = self.url

        community_server_id = str(self.community_server_id)

        active = self.active

        secret = self.secret

        channel_id: None | str | Unset
        if isinstance(self.channel_id, Unset):
            channel_id = UNSET
        else:
            channel_id = self.channel_id

        events: list[str] | None | Unset
        if isinstance(self.events, Unset):
            events = UNSET
        elif isinstance(self.events, list):
            events = self.events

        else:
            events = self.events

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "url": url,
                "community_server_id": community_server_id,
                "active": active,
                "secret": secret,
            }
        )
        if channel_id is not UNSET:
            field_dict["channel_id"] = channel_id
        if events is not UNSET:
            field_dict["events"] = events

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        url = d.pop("url")

        community_server_id = UUID(d.pop("community_server_id"))

        active = d.pop("active")

        secret = d.pop("secret")

        def _parse_channel_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        channel_id = _parse_channel_id(d.pop("channel_id", UNSET))

        def _parse_events(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                events_type_0 = cast(list[str], data)

                return events_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        events = _parse_events(d.pop("events", UNSET))

        webhook_config_secure = cls(
            id=id,
            url=url,
            community_server_id=community_server_id,
            active=active,
            secret=secret,
            channel_id=channel_id,
            events=events,
        )

        webhook_config_secure.additional_properties = d
        return webhook_config_secure

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
