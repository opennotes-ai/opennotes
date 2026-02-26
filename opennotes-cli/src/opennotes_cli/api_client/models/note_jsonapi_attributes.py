from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="NoteJSONAPIAttributes")


@_attrs_define
class NoteJSONAPIAttributes:
    """Note attributes for JSON:API resource.

    Attributes:
        author_id (str):
        summary (str):
        classification (str):
        channel_id (None | str | Unset):
        helpfulness_score (int | Unset):  Default: 0.
        status (str | Unset):  Default: 'NEEDS_MORE_RATINGS'.
        ai_generated (bool | Unset):  Default: False.
        ai_provider (None | str | Unset):
        ai_model (None | str | Unset):
        force_published (bool | Unset):  Default: False.
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
        request_id (None | str | Unset):
        platform_message_id (None | str | Unset):
        force_published_at (datetime.datetime | None | Unset):
        ratings_count (int | Unset):  Default: 0.
        community_server_id (None | str | Unset):
    """

    author_id: str
    summary: str
    classification: str
    channel_id: None | str | Unset = UNSET
    helpfulness_score: int | Unset = 0
    status: str | Unset = "NEEDS_MORE_RATINGS"
    ai_generated: bool | Unset = False
    ai_provider: None | str | Unset = UNSET
    ai_model: None | str | Unset = UNSET
    force_published: bool | Unset = False
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    request_id: None | str | Unset = UNSET
    platform_message_id: None | str | Unset = UNSET
    force_published_at: datetime.datetime | None | Unset = UNSET
    ratings_count: int | Unset = 0
    community_server_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        author_id = self.author_id

        summary = self.summary

        classification = self.classification

        channel_id: None | str | Unset
        if isinstance(self.channel_id, Unset):
            channel_id = UNSET
        else:
            channel_id = self.channel_id

        helpfulness_score = self.helpfulness_score

        status = self.status

        ai_generated = self.ai_generated

        ai_provider: None | str | Unset
        if isinstance(self.ai_provider, Unset):
            ai_provider = UNSET
        else:
            ai_provider = self.ai_provider

        ai_model: None | str | Unset
        if isinstance(self.ai_model, Unset):
            ai_model = UNSET
        else:
            ai_model = self.ai_model

        force_published = self.force_published

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

        request_id: None | str | Unset
        if isinstance(self.request_id, Unset):
            request_id = UNSET
        else:
            request_id = self.request_id

        platform_message_id: None | str | Unset
        if isinstance(self.platform_message_id, Unset):
            platform_message_id = UNSET
        else:
            platform_message_id = self.platform_message_id

        force_published_at: None | str | Unset
        if isinstance(self.force_published_at, Unset):
            force_published_at = UNSET
        elif isinstance(self.force_published_at, datetime.datetime):
            force_published_at = self.force_published_at.isoformat()
        else:
            force_published_at = self.force_published_at

        ratings_count = self.ratings_count

        community_server_id: None | str | Unset
        if isinstance(self.community_server_id, Unset):
            community_server_id = UNSET
        else:
            community_server_id = self.community_server_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "author_id": author_id,
                "summary": summary,
                "classification": classification,
            }
        )
        if channel_id is not UNSET:
            field_dict["channel_id"] = channel_id
        if helpfulness_score is not UNSET:
            field_dict["helpfulness_score"] = helpfulness_score
        if status is not UNSET:
            field_dict["status"] = status
        if ai_generated is not UNSET:
            field_dict["ai_generated"] = ai_generated
        if ai_provider is not UNSET:
            field_dict["ai_provider"] = ai_provider
        if ai_model is not UNSET:
            field_dict["ai_model"] = ai_model
        if force_published is not UNSET:
            field_dict["force_published"] = force_published
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if request_id is not UNSET:
            field_dict["request_id"] = request_id
        if platform_message_id is not UNSET:
            field_dict["platform_message_id"] = platform_message_id
        if force_published_at is not UNSET:
            field_dict["force_published_at"] = force_published_at
        if ratings_count is not UNSET:
            field_dict["ratings_count"] = ratings_count
        if community_server_id is not UNSET:
            field_dict["community_server_id"] = community_server_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        author_id = d.pop("author_id")

        summary = d.pop("summary")

        classification = d.pop("classification")

        def _parse_channel_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        channel_id = _parse_channel_id(d.pop("channel_id", UNSET))

        helpfulness_score = d.pop("helpfulness_score", UNSET)

        status = d.pop("status", UNSET)

        ai_generated = d.pop("ai_generated", UNSET)

        def _parse_ai_provider(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ai_provider = _parse_ai_provider(d.pop("ai_provider", UNSET))

        def _parse_ai_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ai_model = _parse_ai_model(d.pop("ai_model", UNSET))

        force_published = d.pop("force_published", UNSET)

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

        def _parse_request_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        request_id = _parse_request_id(d.pop("request_id", UNSET))

        def _parse_platform_message_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        platform_message_id = _parse_platform_message_id(
            d.pop("platform_message_id", UNSET)
        )

        def _parse_force_published_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                force_published_at_type_0 = isoparse(data)

                return force_published_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        force_published_at = _parse_force_published_at(
            d.pop("force_published_at", UNSET)
        )

        ratings_count = d.pop("ratings_count", UNSET)

        def _parse_community_server_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        community_server_id = _parse_community_server_id(
            d.pop("community_server_id", UNSET)
        )

        note_jsonapi_attributes = cls(
            author_id=author_id,
            summary=summary,
            classification=classification,
            channel_id=channel_id,
            helpfulness_score=helpfulness_score,
            status=status,
            ai_generated=ai_generated,
            ai_provider=ai_provider,
            ai_model=ai_model,
            force_published=force_published,
            created_at=created_at,
            updated_at=updated_at,
            request_id=request_id,
            platform_message_id=platform_message_id,
            force_published_at=force_published_at,
            ratings_count=ratings_count,
            community_server_id=community_server_id,
        )

        note_jsonapi_attributes.additional_properties = d
        return note_jsonapi_attributes

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
