from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="NotePublisherPostCreateAttributes")


@_attrs_define
class NotePublisherPostCreateAttributes:
    """Attributes for creating a note publisher post via JSON:API.

    Attributes:
        note_id (str): UUID of the published note
        original_message_id (str): Original Discord message ID
        channel_id (str): Discord channel ID
        community_server_id (str): Discord server/guild ID (platform ID)
        score_at_post (float): Score at time of posting
        confidence_at_post (str): Confidence level at posting
        success (bool): Whether the post was successful
        auto_post_message_id (None | str | Unset): Auto-posted Discord message ID
        error_message (None | str | Unset): Error message if post failed
    """

    note_id: str
    original_message_id: str
    channel_id: str
    community_server_id: str
    score_at_post: float
    confidence_at_post: str
    success: bool
    auto_post_message_id: None | str | Unset = UNSET
    error_message: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        note_id = self.note_id

        original_message_id = self.original_message_id

        channel_id = self.channel_id

        community_server_id = self.community_server_id

        score_at_post = self.score_at_post

        confidence_at_post = self.confidence_at_post

        success = self.success

        auto_post_message_id: None | str | Unset
        if isinstance(self.auto_post_message_id, Unset):
            auto_post_message_id = UNSET
        else:
            auto_post_message_id = self.auto_post_message_id

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "note_id": note_id,
                "original_message_id": original_message_id,
                "channel_id": channel_id,
                "community_server_id": community_server_id,
                "score_at_post": score_at_post,
                "confidence_at_post": confidence_at_post,
                "success": success,
            }
        )
        if auto_post_message_id is not UNSET:
            field_dict["auto_post_message_id"] = auto_post_message_id
        if error_message is not UNSET:
            field_dict["error_message"] = error_message

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        note_id = d.pop("note_id")

        original_message_id = d.pop("original_message_id")

        channel_id = d.pop("channel_id")

        community_server_id = d.pop("community_server_id")

        score_at_post = d.pop("score_at_post")

        confidence_at_post = d.pop("confidence_at_post")

        success = d.pop("success")

        def _parse_auto_post_message_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        auto_post_message_id = _parse_auto_post_message_id(
            d.pop("auto_post_message_id", UNSET)
        )

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        note_publisher_post_create_attributes = cls(
            note_id=note_id,
            original_message_id=original_message_id,
            channel_id=channel_id,
            community_server_id=community_server_id,
            score_at_post=score_at_post,
            confidence_at_post=confidence_at_post,
            success=success,
            auto_post_message_id=auto_post_message_id,
            error_message=error_message,
        )

        return note_publisher_post_create_attributes
