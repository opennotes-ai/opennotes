from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="WebhookCreateRequest")


@_attrs_define
class WebhookCreateRequest:
    """
    Attributes:
        url (str): Webhook URL
        secret (str): Webhook secret
        platform_community_server_id (str): Platform-specific community server ID (Discord guild ID, subreddit name,
            etc.)
        channel_id (None | str | Unset): Channel ID (Discord channel ID, etc.)
        events (list[str] | None | Unset): Event types this webhook subscribes to. Null means all events.
    """

    url: str
    secret: str
    platform_community_server_id: str
    channel_id: None | str | Unset = UNSET
    events: list[str] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        url = self.url

        secret = self.secret

        platform_community_server_id = self.platform_community_server_id

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

        field_dict.update(
            {
                "url": url,
                "secret": secret,
                "platform_community_server_id": platform_community_server_id,
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
        url = d.pop("url")

        secret = d.pop("secret")

        platform_community_server_id = d.pop("platform_community_server_id")

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

        webhook_create_request = cls(
            url=url,
            secret=secret,
            platform_community_server_id=platform_community_server_id,
            channel_id=channel_id,
            events=events,
        )

        return webhook_create_request
