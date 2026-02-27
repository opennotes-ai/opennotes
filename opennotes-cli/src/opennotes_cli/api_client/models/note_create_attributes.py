from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..models.note_classification import NoteClassification
from ..types import UNSET, Unset

T = TypeVar("T", bound="NoteCreateAttributes")


@_attrs_define
class NoteCreateAttributes:
    """Attributes for creating a note via JSON:API.

    Attributes:
        summary (str): Note summary text
        classification (NoteClassification):
        community_server_id (UUID): Community server ID
        author_id (UUID): Author's user profile ID
        channel_id (None | str | Unset): Discord channel ID
        request_id (None | str | Unset): Request ID this note responds to
    """

    summary: str
    classification: NoteClassification
    community_server_id: UUID
    author_id: UUID
    channel_id: None | str | Unset = UNSET
    request_id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        summary = self.summary

        classification = self.classification.value

        community_server_id = str(self.community_server_id)

        author_id = str(self.author_id)

        channel_id: None | str | Unset
        if isinstance(self.channel_id, Unset):
            channel_id = UNSET
        else:
            channel_id = self.channel_id

        request_id: None | str | Unset
        if isinstance(self.request_id, Unset):
            request_id = UNSET
        else:
            request_id = self.request_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "summary": summary,
                "classification": classification,
                "community_server_id": community_server_id,
                "author_id": author_id,
            }
        )
        if channel_id is not UNSET:
            field_dict["channel_id"] = channel_id
        if request_id is not UNSET:
            field_dict["request_id"] = request_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        summary = d.pop("summary")

        classification = NoteClassification(d.pop("classification"))

        community_server_id = UUID(d.pop("community_server_id"))

        author_id = UUID(d.pop("author_id"))

        def _parse_channel_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        channel_id = _parse_channel_id(d.pop("channel_id", UNSET))

        def _parse_request_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        request_id = _parse_request_id(d.pop("request_id", UNSET))

        note_create_attributes = cls(
            summary=summary,
            classification=classification,
            community_server_id=community_server_id,
            author_id=author_id,
            channel_id=channel_id,
            request_id=request_id,
        )

        return note_create_attributes
