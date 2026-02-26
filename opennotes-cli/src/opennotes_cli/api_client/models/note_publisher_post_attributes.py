from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="NotePublisherPostAttributes")


@_attrs_define
class NotePublisherPostAttributes:
    """Note publisher post attributes for JSON:API resource.

    Attributes:
        note_id (str):
        original_message_id (str):
        channel_id (str):
        community_server_id (str):
        score_at_post (float):
        confidence_at_post (str):
        success (bool):
        auto_post_message_id (None | str | Unset):
        posted_at (datetime.datetime | None | Unset):
        error_message (None | str | Unset):
    """

    note_id: str
    original_message_id: str
    channel_id: str
    community_server_id: str
    score_at_post: float
    confidence_at_post: str
    success: bool
    auto_post_message_id: None | str | Unset = UNSET
    posted_at: datetime.datetime | None | Unset = UNSET
    error_message: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

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

        posted_at: None | str | Unset
        if isinstance(self.posted_at, Unset):
            posted_at = UNSET
        elif isinstance(self.posted_at, datetime.datetime):
            posted_at = self.posted_at.isoformat()
        else:
            posted_at = self.posted_at

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
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
        if posted_at is not UNSET:
            field_dict["posted_at"] = posted_at
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

        def _parse_posted_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                posted_at_type_0 = isoparse(data)

                return posted_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        posted_at = _parse_posted_at(d.pop("posted_at", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        note_publisher_post_attributes = cls(
            note_id=note_id,
            original_message_id=original_message_id,
            channel_id=channel_id,
            community_server_id=community_server_id,
            score_at_post=score_at_post,
            confidence_at_post=confidence_at_post,
            success=success,
            auto_post_message_id=auto_post_message_id,
            posted_at=posted_at,
            error_message=error_message,
        )

        note_publisher_post_attributes.additional_properties = d
        return note_publisher_post_attributes

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
