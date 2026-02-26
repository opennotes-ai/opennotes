from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="NoteData")


@_attrs_define
class NoteData:
    """
    Attributes:
        note_id (int):
        note_author_participant_id (str):
        created_at_millis (int):
        tweet_id (int):
        summary (str):
        classification (str):
    """

    note_id: int
    note_author_participant_id: str
    created_at_millis: int
    tweet_id: int
    summary: str
    classification: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        note_id = self.note_id

        note_author_participant_id = self.note_author_participant_id

        created_at_millis = self.created_at_millis

        tweet_id = self.tweet_id

        summary = self.summary

        classification = self.classification

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "noteId": note_id,
                "noteAuthorParticipantId": note_author_participant_id,
                "createdAtMillis": created_at_millis,
                "tweetId": tweet_id,
                "summary": summary,
                "classification": classification,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        note_id = d.pop("noteId")

        note_author_participant_id = d.pop("noteAuthorParticipantId")

        created_at_millis = d.pop("createdAtMillis")

        tweet_id = d.pop("tweetId")

        summary = d.pop("summary")

        classification = d.pop("classification")

        note_data = cls(
            note_id=note_id,
            note_author_participant_id=note_author_participant_id,
            created_at_millis=created_at_millis,
            tweet_id=tweet_id,
            summary=summary,
            classification=classification,
        )

        note_data.additional_properties = d
        return note_data

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
