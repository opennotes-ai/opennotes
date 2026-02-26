from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="HybridSearchMatchResource")


@_attrs_define
class HybridSearchMatchResource:
    """JSON:API-compatible fact-check match in hybrid search results.

    Attributes:
        id (str): Fact-check item UUID
        dataset_name (str): Source dataset (e.g., 'snopes')
        dataset_tags (list[str]): Dataset tags
        title (str): Fact-check article title
        content (str): Fact-check content
        cc_score (float): Convex Combination score fusing semantic and keyword rankings
        summary (None | str | Unset): Brief summary
        rating (None | str | Unset): Fact-check verdict
        source_url (None | str | Unset): URL to original article
        published_date (datetime.datetime | None | Unset): Publication date
        author (None | str | Unset): Author name
    """

    id: str
    dataset_name: str
    dataset_tags: list[str]
    title: str
    content: str
    cc_score: float
    summary: None | str | Unset = UNSET
    rating: None | str | Unset = UNSET
    source_url: None | str | Unset = UNSET
    published_date: datetime.datetime | None | Unset = UNSET
    author: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        dataset_name = self.dataset_name

        dataset_tags = self.dataset_tags

        title = self.title

        content = self.content

        cc_score = self.cc_score

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

        source_url: None | str | Unset
        if isinstance(self.source_url, Unset):
            source_url = UNSET
        else:
            source_url = self.source_url

        published_date: None | str | Unset
        if isinstance(self.published_date, Unset):
            published_date = UNSET
        elif isinstance(self.published_date, datetime.datetime):
            published_date = self.published_date.isoformat()
        else:
            published_date = self.published_date

        author: None | str | Unset
        if isinstance(self.author, Unset):
            author = UNSET
        else:
            author = self.author

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "dataset_name": dataset_name,
                "dataset_tags": dataset_tags,
                "title": title,
                "content": content,
                "cc_score": cc_score,
            }
        )
        if summary is not UNSET:
            field_dict["summary"] = summary
        if rating is not UNSET:
            field_dict["rating"] = rating
        if source_url is not UNSET:
            field_dict["source_url"] = source_url
        if published_date is not UNSET:
            field_dict["published_date"] = published_date
        if author is not UNSET:
            field_dict["author"] = author

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        dataset_name = d.pop("dataset_name")

        dataset_tags = cast(list[str], d.pop("dataset_tags"))

        title = d.pop("title")

        content = d.pop("content")

        cc_score = d.pop("cc_score")

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

        def _parse_source_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source_url = _parse_source_url(d.pop("source_url", UNSET))

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

        def _parse_author(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        author = _parse_author(d.pop("author", UNSET))

        hybrid_search_match_resource = cls(
            id=id,
            dataset_name=dataset_name,
            dataset_tags=dataset_tags,
            title=title,
            content=content,
            cc_score=cc_score,
            summary=summary,
            rating=rating,
            source_url=source_url,
            published_date=published_date,
            author=author,
        )

        hybrid_search_match_resource.additional_properties = d
        return hybrid_search_match_resource

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
