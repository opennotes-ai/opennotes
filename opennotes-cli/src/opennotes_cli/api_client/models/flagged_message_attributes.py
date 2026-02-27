from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.conversation_flashpoint_match import ConversationFlashpointMatch
    from ..models.open_ai_moderation_match import OpenAIModerationMatch
    from ..models.similarity_match import SimilarityMatch


T = TypeVar("T", bound="FlaggedMessageAttributes")


@_attrs_define
class FlaggedMessageAttributes:
    """Attributes for a flagged message resource.

    Attributes:
        channel_id (str): Channel ID where message was found
        content (str): Message content
        author_id (str): Author ID
        timestamp (datetime.datetime): Message timestamp
        matches (list[ConversationFlashpointMatch | OpenAIModerationMatch | SimilarityMatch] | Unset): List of match
            results from different scan types
    """

    channel_id: str
    content: str
    author_id: str
    timestamp: datetime.datetime
    matches: (
        list[ConversationFlashpointMatch | OpenAIModerationMatch | SimilarityMatch]
        | Unset
    ) = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.open_ai_moderation_match import OpenAIModerationMatch
        from ..models.similarity_match import SimilarityMatch

        channel_id = self.channel_id

        content = self.content

        author_id = self.author_id

        timestamp = self.timestamp.isoformat()

        matches: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.matches, Unset):
            matches = []
            for matches_item_data in self.matches:
                matches_item: dict[str, Any]
                if isinstance(matches_item_data, SimilarityMatch):
                    matches_item = matches_item_data.to_dict()
                elif isinstance(matches_item_data, OpenAIModerationMatch):
                    matches_item = matches_item_data.to_dict()
                else:
                    matches_item = matches_item_data.to_dict()

                matches.append(matches_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "channel_id": channel_id,
                "content": content,
                "author_id": author_id,
                "timestamp": timestamp,
            }
        )
        if matches is not UNSET:
            field_dict["matches"] = matches

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conversation_flashpoint_match import ConversationFlashpointMatch
        from ..models.open_ai_moderation_match import OpenAIModerationMatch
        from ..models.similarity_match import SimilarityMatch

        d = dict(src_dict)
        channel_id = d.pop("channel_id")

        content = d.pop("content")

        author_id = d.pop("author_id")

        timestamp = isoparse(d.pop("timestamp"))

        _matches = d.pop("matches", UNSET)
        matches: (
            list[ConversationFlashpointMatch | OpenAIModerationMatch | SimilarityMatch]
            | Unset
        ) = UNSET
        if _matches is not UNSET:
            matches = []
            for matches_item_data in _matches:

                def _parse_matches_item(
                    data: object,
                ) -> (
                    ConversationFlashpointMatch
                    | OpenAIModerationMatch
                    | SimilarityMatch
                ):
                    try:
                        if not isinstance(data, dict):
                            raise TypeError()
                        matches_item_type_0 = SimilarityMatch.from_dict(data)

                        return matches_item_type_0
                    except (TypeError, ValueError, AttributeError, KeyError):
                        pass
                    try:
                        if not isinstance(data, dict):
                            raise TypeError()
                        matches_item_type_1 = OpenAIModerationMatch.from_dict(data)

                        return matches_item_type_1
                    except (TypeError, ValueError, AttributeError, KeyError):
                        pass
                    if not isinstance(data, dict):
                        raise TypeError()
                    matches_item_type_2 = ConversationFlashpointMatch.from_dict(data)

                    return matches_item_type_2

                matches_item = _parse_matches_item(matches_item_data)

                matches.append(matches_item)

        flagged_message_attributes = cls(
            channel_id=channel_id,
            content=content,
            author_id=author_id,
            timestamp=timestamp,
            matches=matches,
        )

        flagged_message_attributes.additional_properties = d
        return flagged_message_attributes

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
