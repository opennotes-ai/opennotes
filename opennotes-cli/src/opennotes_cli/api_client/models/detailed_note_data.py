from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.detailed_note_data_message_metadata_type_0 import (
        DetailedNoteDataMessageMetadataType0,
    )
    from ..models.detailed_rating_data import DetailedRatingData


T = TypeVar("T", bound="DetailedNoteData")


@_attrs_define
class DetailedNoteData:
    """
    Attributes:
        note_id (str):
        summary (str):
        classification (str):
        status (str):
        helpfulness_score (float):
        author_agent_name (str):
        author_agent_profile_id (str):
        request_id (None | Unset | UUID):
        message_metadata (DetailedNoteDataMessageMetadataType0 | None | Unset):
        created_at (datetime.datetime | None | Unset):
        ratings (list[DetailedRatingData] | Unset):
    """

    note_id: str
    summary: str
    classification: str
    status: str
    helpfulness_score: float
    author_agent_name: str
    author_agent_profile_id: str
    request_id: None | Unset | UUID = UNSET
    message_metadata: DetailedNoteDataMessageMetadataType0 | None | Unset = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    ratings: list[DetailedRatingData] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.detailed_note_data_message_metadata_type_0 import (
            DetailedNoteDataMessageMetadataType0,
        )

        note_id = self.note_id

        summary = self.summary

        classification = self.classification

        status = self.status

        helpfulness_score = self.helpfulness_score

        author_agent_name = self.author_agent_name

        author_agent_profile_id = self.author_agent_profile_id

        request_id: None | str | Unset
        if isinstance(self.request_id, Unset):
            request_id = UNSET
        elif isinstance(self.request_id, UUID):
            request_id = str(self.request_id)
        else:
            request_id = self.request_id

        message_metadata: dict[str, Any] | None | Unset
        if isinstance(self.message_metadata, Unset):
            message_metadata = UNSET
        elif isinstance(self.message_metadata, DetailedNoteDataMessageMetadataType0):
            message_metadata = self.message_metadata.to_dict()
        else:
            message_metadata = self.message_metadata

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        ratings: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.ratings, Unset):
            ratings = []
            for ratings_item_data in self.ratings:
                ratings_item = ratings_item_data.to_dict()
                ratings.append(ratings_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "note_id": note_id,
                "summary": summary,
                "classification": classification,
                "status": status,
                "helpfulness_score": helpfulness_score,
                "author_agent_name": author_agent_name,
                "author_agent_profile_id": author_agent_profile_id,
            }
        )
        if request_id is not UNSET:
            field_dict["request_id"] = request_id
        if message_metadata is not UNSET:
            field_dict["message_metadata"] = message_metadata
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if ratings is not UNSET:
            field_dict["ratings"] = ratings

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.detailed_note_data_message_metadata_type_0 import (
            DetailedNoteDataMessageMetadataType0,
        )
        from ..models.detailed_rating_data import DetailedRatingData

        d = dict(src_dict)
        note_id = d.pop("note_id")

        summary = d.pop("summary")

        classification = d.pop("classification")

        status = d.pop("status")

        helpfulness_score = d.pop("helpfulness_score")

        author_agent_name = d.pop("author_agent_name")

        author_agent_profile_id = d.pop("author_agent_profile_id")

        def _parse_request_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                request_id_type_0 = UUID(data)

                return request_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        request_id = _parse_request_id(d.pop("request_id", UNSET))

        def _parse_message_metadata(
            data: object,
        ) -> DetailedNoteDataMessageMetadataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                message_metadata_type_0 = (
                    DetailedNoteDataMessageMetadataType0.from_dict(data)
                )

                return message_metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DetailedNoteDataMessageMetadataType0 | None | Unset, data)

        message_metadata = _parse_message_metadata(d.pop("message_metadata", UNSET))

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

        _ratings = d.pop("ratings", UNSET)
        ratings: list[DetailedRatingData] | Unset = UNSET
        if _ratings is not UNSET:
            ratings = []
            for ratings_item_data in _ratings:
                ratings_item = DetailedRatingData.from_dict(ratings_item_data)

                ratings.append(ratings_item)

        detailed_note_data = cls(
            note_id=note_id,
            summary=summary,
            classification=classification,
            status=status,
            helpfulness_score=helpfulness_score,
            author_agent_name=author_agent_name,
            author_agent_profile_id=author_agent_profile_id,
            request_id=request_id,
            message_metadata=message_metadata,
            created_at=created_at,
            ratings=ratings,
        )

        detailed_note_data.additional_properties = d
        return detailed_note_data

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
