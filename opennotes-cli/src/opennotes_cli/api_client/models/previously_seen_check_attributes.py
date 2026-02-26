from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="PreviouslySeenCheckAttributes")


@_attrs_define
class PreviouslySeenCheckAttributes:
    """Attributes for checking previously seen messages via JSON:API.

    Attributes:
        message_text (str): Message text to check
        platform_community_server_id (str): Platform-specific community server ID (e.g., Discord guild ID)
        channel_id (str): Platform-specific channel ID
    """

    message_text: str
    platform_community_server_id: str
    channel_id: str

    def to_dict(self) -> dict[str, Any]:
        message_text = self.message_text

        platform_community_server_id = self.platform_community_server_id

        channel_id = self.channel_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "message_text": message_text,
                "platform_community_server_id": platform_community_server_id,
                "channel_id": channel_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message_text = d.pop("message_text")

        platform_community_server_id = d.pop("platform_community_server_id")

        channel_id = d.pop("channel_id")

        previously_seen_check_attributes = cls(
            message_text=message_text,
            platform_community_server_id=platform_community_server_id,
            channel_id=channel_id,
        )

        return previously_seen_check_attributes
