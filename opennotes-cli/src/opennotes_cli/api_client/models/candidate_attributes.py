from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.candidate_attributes_predicted_ratings_type_0 import (
        CandidateAttributesPredictedRatingsType0,
    )


T = TypeVar("T", bound="CandidateAttributes")


@_attrs_define
class CandidateAttributes:
    """JSON:API attributes for a fact-check candidate.

    Attributes:
        source_url (str): URL to the original article
        title (str): Article title from source
        dataset_name (str): Source dataset identifier
        status (str): Processing status
        created_at (datetime.datetime): Record creation timestamp
        updated_at (datetime.datetime): Last update timestamp
        content (None | str | Unset): Scraped article body
        summary (None | str | Unset): Optional summary
        rating (None | str | Unset): Human-approved fact-check verdict
        rating_details (None | str | Unset): Original rating before normalization
        predicted_ratings (CandidateAttributesPredictedRatingsType0 | None | Unset): ML/AI predicted ratings as {rating:
            probability}
        published_date (datetime.datetime | None | Unset): Publication date
        dataset_tags (list[str] | Unset): Tags for filtering
        original_id (None | str | Unset): ID from source dataset
        error_message (None | str | Unset): Error details if failed
    """

    source_url: str
    title: str
    dataset_name: str
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    content: None | str | Unset = UNSET
    summary: None | str | Unset = UNSET
    rating: None | str | Unset = UNSET
    rating_details: None | str | Unset = UNSET
    predicted_ratings: CandidateAttributesPredictedRatingsType0 | None | Unset = UNSET
    published_date: datetime.datetime | None | Unset = UNSET
    dataset_tags: list[str] | Unset = UNSET
    original_id: None | str | Unset = UNSET
    error_message: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.candidate_attributes_predicted_ratings_type_0 import (
            CandidateAttributesPredictedRatingsType0,
        )

        source_url = self.source_url

        title = self.title

        dataset_name = self.dataset_name

        status = self.status

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        content: None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        else:
            content = self.content

        summary: None | str | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        else:
            summary = self.summary

        rating: None | str | Unset
        if isinstance(self.rating, Unset):
            rating = UNSET
        else:
            rating = self.rating

        rating_details: None | str | Unset
        if isinstance(self.rating_details, Unset):
            rating_details = UNSET
        else:
            rating_details = self.rating_details

        predicted_ratings: dict[str, Any] | None | Unset
        if isinstance(self.predicted_ratings, Unset):
            predicted_ratings = UNSET
        elif isinstance(
            self.predicted_ratings, CandidateAttributesPredictedRatingsType0
        ):
            predicted_ratings = self.predicted_ratings.to_dict()
        else:
            predicted_ratings = self.predicted_ratings

        published_date: None | str | Unset
        if isinstance(self.published_date, Unset):
            published_date = UNSET
        elif isinstance(self.published_date, datetime.datetime):
            published_date = self.published_date.isoformat()
        else:
            published_date = self.published_date

        dataset_tags: list[str] | Unset = UNSET
        if not isinstance(self.dataset_tags, Unset):
            dataset_tags = self.dataset_tags

        original_id: None | str | Unset
        if isinstance(self.original_id, Unset):
            original_id = UNSET
        else:
            original_id = self.original_id

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source_url": source_url,
                "title": title,
                "dataset_name": dataset_name,
                "status": status,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if content is not UNSET:
            field_dict["content"] = content
        if summary is not UNSET:
            field_dict["summary"] = summary
        if rating is not UNSET:
            field_dict["rating"] = rating
        if rating_details is not UNSET:
            field_dict["rating_details"] = rating_details
        if predicted_ratings is not UNSET:
            field_dict["predicted_ratings"] = predicted_ratings
        if published_date is not UNSET:
            field_dict["published_date"] = published_date
        if dataset_tags is not UNSET:
            field_dict["dataset_tags"] = dataset_tags
        if original_id is not UNSET:
            field_dict["original_id"] = original_id
        if error_message is not UNSET:
            field_dict["error_message"] = error_message

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.candidate_attributes_predicted_ratings_type_0 import (
            CandidateAttributesPredictedRatingsType0,
        )

        d = dict(src_dict)
        source_url = d.pop("source_url")

        title = d.pop("title")

        dataset_name = d.pop("dataset_name")

        status = d.pop("status")

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))

        def _parse_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        def _parse_rating(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rating = _parse_rating(d.pop("rating", UNSET))

        def _parse_rating_details(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rating_details = _parse_rating_details(d.pop("rating_details", UNSET))

        def _parse_predicted_ratings(
            data: object,
        ) -> CandidateAttributesPredictedRatingsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                predicted_ratings_type_0 = (
                    CandidateAttributesPredictedRatingsType0.from_dict(data)
                )

                return predicted_ratings_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CandidateAttributesPredictedRatingsType0 | None | Unset, data)

        predicted_ratings = _parse_predicted_ratings(d.pop("predicted_ratings", UNSET))

        def _parse_published_date(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                published_date_type_0 = isoparse(data)

                return published_date_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        published_date = _parse_published_date(d.pop("published_date", UNSET))

        dataset_tags = cast(list[str], d.pop("dataset_tags", UNSET))

        def _parse_original_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        original_id = _parse_original_id(d.pop("original_id", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        candidate_attributes = cls(
            source_url=source_url,
            title=title,
            dataset_name=dataset_name,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            content=content,
            summary=summary,
            rating=rating,
            rating_details=rating_details,
            predicted_ratings=predicted_ratings,
            published_date=published_date,
            dataset_tags=dataset_tags,
            original_id=original_id,
            error_message=error_message,
        )

        candidate_attributes.additional_properties = d
        return candidate_attributes

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
